import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from core import paths
from core.event_bus import EventBus
from core.settings import Settings
from personality.dialogue import DialogueManager
from personality.greeter import LoginGreeter
from tests.helpers import make_processor


class FakeTimer:
    def __init__(self, seconds, function):
        self.function, self.started, self.cancelled, self.daemon = function, False, False, False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True


class FakeSpeech:
    def __init__(self):
        self.said = []

    def say(self, text=None, **kw):
        self.said.append((text, kw))
        return True


def build(mood="Friendly", style="personality", mature=False, state=None):
    bus = EventBus()
    s = Settings(Path("nope.json")).load()
    s.set("personality.mood_mode", "fixed")
    s.set("personality.mood", mood)
    s.set("personality.style", style)
    s.set("speech.allow_mature", mature)
    d = DialogueManager(paths.VOICEPACKS_DIR / "default").load()
    speech = FakeSpeech()
    timers = []
    def timer(seconds, fn):
        t = FakeTimer(seconds, fn); timers.append(t); return t
    g = LoginGreeter(bus, speech, d, s, state_provider=lambda: state, timer_factory=timer)
    g.attach()
    return g, bus, speech, timers, d, s


LOAD = {"Commander": "Ada", "Ship": "python", "Ship_Localised": "Python", "ShipName": "Stardust"}


def texts(d, key):
    return [l.text for l in d.lines[key]]


class GreeterTests(unittest.TestCase):
    def test_docked_greeting_names_ship_system_and_station(self):
        g, bus, speech, timers, d, s = build()
        bus.publish("LoadGame", LOAD, "low")
        self.assertEqual(speech.said, [])                     # waits for Location
        bus.publish("Location", {"StarSystem": "Shinrarta Dezhra", "Docked": True, "StationName": "Jameson Memorial", "Landed": False}, "low")
        text = speech.said[0][0]
        self.assertIn("Python called Stardust", text)
        self.assertIn("Shinrarta Dezhra", text)
        self.assertIn("Jameson Memorial", text)
        self.assertIn(" || ", text)
        self.assertTrue(timers[0].cancelled)

    def test_landed_says_where_you_landed(self):
        g, bus, speech, *_ = build()
        bus.publish("LoadGame", LOAD, "low")
        bus.publish("Location", {"StarSystem": "Sol", "Docked": False, "Landed": True, "Body": "Mars 3 a"}, "low")
        self.assertIn("Mars 3 a", speech.said[0][0])

    def test_in_space(self):
        g, bus, speech, *_ = build()
        bus.publish("LoadGame", LOAD, "low")
        bus.publish("Location", {"StarSystem": "Sol", "Docked": False, "Landed": False}, "low")
        text = speech.said[0][0]
        self.assertIn("Sol", text)
        self.assertNotIn("docked", text.lower())

    def test_bad_mood_greeting_includes_the_mood(self):
        g, bus, speech, timers, d, s = build("Frustrated")
        bus.publish("LoadGame", LOAD, "low")
        bus.publish("Location", {"StarSystem": "Sol", "Docked": False, "Landed": False}, "low")
        feeling = speech.said[0][0].split(" || ")[1]
        self.assertIn(feeling, texts(d, "Login_Mood_Frustrated"))
        self.assertFalse(any(l.mature and l.text == feeling for l in d.lines["Login_Mood_Frustrated"]))   # strong language off

    def test_strong_language_allowed_in_bad_mood(self):
        seen = set()
        for _ in range(60):
            g, bus, speech, *_ = build("Frustrated", mature=True)
            bus.publish("LoadGame", LOAD, "low")
            bus.publish("Location", {"StarSystem": "Sol", "Docked": False}, "low")
            seen.add(speech.said[0][0].split(" || ")[1])
        self.assertTrue(any("Bloody" in t or "pissed" in t for t in seen))

    def test_info_style_is_plain(self):
        g, bus, speech, timers, d, s = build("Frustrated", style="info")
        bus.publish("LoadGame", LOAD, "low")
        bus.publish("Location", {"StarSystem": "Sol", "Docked": True, "StationName": "Daedalus"}, "low")
        text = speech.said[0][0]
        self.assertNotIn("||", text)
        self.assertIn("Daedalus", text)
        for line in texts(d, "Login_Open_Frustrated"):
            self.assertNotIn(line, text)

    def test_wanted_warning(self):
        g, bus, speech, *_ = build()
        bus.publish("LoadGame", LOAD, "low")
        bus.publish("Location", {"StarSystem": "Sol", "Docked": False, "Wanted": True}, "low")
        self.assertTrue(any(w in speech.said[0][0] for w in texts(g.dialogue, "Login_Wanted")))

    def test_falls_back_when_location_never_arrives(self):
        state = SimpleNamespace(ship="Python", ship_name="Stardust", system="Sol", station="Daedalus", docked=True)
        g, bus, speech, timers, *_ = build(state=state)
        bus.publish("LoadGame", LOAD, "low")
        timers[0].function()
        self.assertIn("Daedalus", speech.said[0][0])

    def test_only_one_greeting_and_not_when_off(self):
        g, bus, speech, timers, d, s = build()
        bus.publish("LoadGame", LOAD, "low")
        bus.publish("Location", {"StarSystem": "Sol"}, "low")
        bus.publish("Location", {"StarSystem": "Sol"}, "low")      # e.g. after respawning
        bus.publish("LoadGame", LOAD, "low")                        # too soon
        self.assertEqual(len(speech.said), 1)
        g2, bus2, speech2, *_ = build()
        g2.settings.set("personality.login_greeting", False)
        bus2.publish("LoadGame", LOAD, "low")
        self.assertEqual(speech2.said, [])

    def test_name_token_and_pet_names_do_not_break_text(self):
        g, bus, speech, *_ = build("Close")
        bus.publish("LoadGame", LOAD, "low")
        bus.publish("Location", {"StarSystem": "Sol"}, "low")
        self.assertNotIn("@NAME@", speech.said[0][0])
        self.assertNotIn("{", speech.said[0][0])


class ThroughTheRealProcessor(unittest.TestCase):
    def test_journal_lines_reach_the_greeter(self):
        processor, bus, heard = make_processor()
        s = Settings(Path("nope.json")).load()
        d = DialogueManager(paths.VOICEPACKS_DIR / "default").load()
        speech = FakeSpeech()
        g = LoginGreeter(bus, speech, d, s, state_provider=lambda: processor.state, timer_factory=FakeTimer)
        g.attach()
        processor.handle_line(json.dumps({"timestamp": "t", "event": "LoadGame", "Commander": "Demo", "Ship": "Anaconda",
                                          "Ship_Localised": "Anaconda", "ShipName": "Demo Ship"}))
        processor.handle_line(json.dumps({"timestamp": "t", "event": "Location", "StarSystem": "Sol", "Docked": True,
                                          "StationName": "Daedalus"}))
        self.assertIn("Daedalus", speech.said[0][0])
        self.assertIn("Anaconda", speech.said[0][0])

    def test_landed_is_worked_out_from_the_latitude(self):
        processor, bus, heard = make_processor()
        processor.handle_line(json.dumps({"timestamp": "t", "event": "Location", "StarSystem": "Sol", "Docked": False,
                                          "Body": "Mars 1", "Latitude": 10.5, "Longitude": 20.1}))
        self.assertTrue(heard[-1].data["Landed"])


if __name__ == "__main__":
    unittest.main()
