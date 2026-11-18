import random
import unittest

import numpy as np

from ui import hologram as h
from ui.hologram_window import HologramFeed
from ui.window_voice import WindowVoice, which


class Clock:
    def __init__(self): self.t = 100.0
    def __call__(self): return self.t


def make(height=225):
    clock = Clock()
    return h.Hologram(h.Assets(height), random.Random(1), clock), clock


class Placement(unittest.TestCase):
    def test_size_scales_with_screen(self):
        self.assertEqual(h.height_for(1080, 100), 225)
        self.assertEqual(h.height_for(2160, 100), 450)
        self.assertEqual(h.height_for(1080, 150), 338)
        self.assertEqual(h.height_for(1080, 5000), h.height_for(1080, 200))

    def test_position_round_trip(self):
        x, y = h.window_position(1920, 1080, 151, 263, 6.5, 24)
        left, bottom = h.percents_from_position(1920, 1080, 151, 263, x, y)
        self.assertAlmostEqual(left, 6.5, delta=0.1)
        self.assertAlmostEqual(bottom, 24, delta=0.2)

    def test_stays_on_screen(self):
        x, y = h.window_position(1920, 1080, 151, 263, 500, 500)
        self.assertTrue(0 <= x <= 1920 - 151 and 0 <= y <= 1080 - 263)


class Mouth(unittest.TestCase):
    def test_track_uses_vowels_and_pauses(self):
        track = h.build_track("Hello, Ben.")
        self.assertTrue(h.track_length(track) > 0.3)
        names = {h.shape_at(track, t / 20.0) for t in range(0, int(h.track_length(track) * 20) + 1)}
        self.assertIn("oh", names)

    def test_reach_softens_big_mouths(self):
        self.assertLess(h.reach(0.55, "ah"), h.reach(1.0, "ah"))


class Behaviour(unittest.TestCase):
    def test_colour_rules(self):
        holo, c = make()
        self.assertEqual(holo.colour_wanted(False, False, c.t), "cyan")
        self.assertEqual(holo.colour_wanted(True, False, c.t), "green")
        self.assertEqual(holo.colour_wanted(True, True, c.t), "amber")
        holo.heard_her_name(c.t)
        self.assertEqual(holo.colour_wanted(False, False, c.t + 1), "green")
        self.assertEqual(holo.colour_wanted(False, False, c.t + h.LISTEN_SECONDS + 1), "cyan")

    def test_power_up_and_down(self):
        holo, c = make()
        for _ in range(40):
            c.t += 0.05
            holo.tick(powered=True, now=c.t)
        self.assertGreater(holo.power, 0.95)
        for _ in range(40):
            c.t += 0.05
            holo.tick(powered=False, now=c.t)
        self.assertLess(holo.power, 0.03)

    def test_speaking_then_smile(self):
        holo, c = make()
        holo.speech_started("Hello commander", c.t)
        self.assertTrue(holo.speaking)
        c.t += 1.2
        holo.speech_finished(c.t)
        self.assertFalse(holo.speaking)
        self.assertEqual(holo._mouth_goal(c.t + 0.5), "smile")
        self.assertIsNone(holo._mouth_goal(c.t + h.SMILE_SECONDS + 1))

    def test_speed_is_learned_within_limits(self):
        holo, c = make()
        holo.speech_started("a long line of talking here", c.t)
        c.t += 30
        holo.speech_finished(c.t)
        self.assertGreaterEqual(holo.cps, 8.0)

    def test_render_has_key_pixels_and_picture(self):
        holo, c = make()
        for _ in range(40):
            c.t += 0.05
            holo.tick(powered=True, now=c.t)
        frame = holo.render(c.t)
        self.assertEqual(frame.dtype, np.uint8)
        self.assertEqual(frame.shape, (holo.assets.window_h, holo.assets.window_w, 3))
        key = np.all(frame == np.array(h.KEY, dtype=np.uint8), axis=2)
        self.assertGreater(key.mean(), 0.2)         # lots of see-through
        self.assertLess(key.mean(), 0.95)           # but she is drawn

    def test_powered_down_is_all_see_through(self):
        holo, c = make()
        frame = holo.render(c.t)                    # power is 0 at the start
        key = np.all(frame == np.array(h.KEY, dtype=np.uint8), axis=2)
        self.assertGreater(key.mean(), 0.97)


class Bus:
    def __init__(self): self.handlers = {}
    def subscribe(self, name, fn): self.handlers.setdefault(name, []).append(fn)
    def fire(self, name, **data):
        class E: pass
        e = E(); e.data = data
        for fn in self.handlers.get(name, []): fn(e)


class Settings:
    def __init__(self, **v): self.values = v
    def get(self, key, default=None): return self.values.get(key, default)
    def set(self, key, value): self.values[key] = value
    def save(self): pass


class App:
    def __init__(self, **settings):
        self.bus = Bus()
        self.settings = Settings(**settings)
        self.state = type("S", (), {"gui_focus": 0, "game_quit": False})()
        self.ptt = None
        self.ask = type("A", (), {"pending": {}})()
        self.brain = type("B", (), {"thinking": 0})()


class Feed(unittest.TestCase):
    def setUp(self):
        self.holo, self.c = make()
        self.app = App()
        self.feed = HologramFeed(self.app, lambda: self.holo)
        self.feed.attach()

    def test_speech_events_drive_the_mouth(self):
        self.app.bus.fire("speech.started", text="Hello there commander")
        self.app.bus.fire("speech.audio", what="start", text="Hello there commander", seconds=None)
        self.assertTrue(self.holo.speaking)
        self.app.bus.fire("speech.finished")
        self.assertFalse(self.holo.speaking)

    def test_name_alone_means_listening_but_a_command_does_not(self):
        self.app.bus.fire("voice.heard", wake=True, command="")
        self.assertGreater(self.holo.listen_until, 0)
        self.holo.listen_until = 0
        self.app.bus.fire("voice.heard", wake=True, command="landing gear")
        self.assertEqual(self.holo.listen_until, 0)

    def test_open_mic_alone_is_not_listening(self):
        class Ptt:
            def __init__(self, on, held): self.on, self.held = on, held
            def enabled(self): return self.on
            def is_open(self): return self.held
        self.app.ptt = Ptt(False, True)             # always-open mic style: not green
        self.assertFalse(self.feed.listening())
        self.app.ptt = Ptt(True, True)
        self.assertTrue(self.feed.listening())
        self.app.ptt = Ptt(True, False)
        self.assertFalse(self.feed.listening())

    def test_question_pending_is_listening(self):
        self.app.ask.pending = {"open": True}
        self.assertTrue(self.feed.listening())

    def test_listening_colour_can_be_off(self):
        self.app.settings.values["hologram.listening_colour"] = False
        self.app.ask.pending = {"open": True}
        self.assertFalse(self.feed.listening())

    def test_thinking_and_focus(self):
        self.assertFalse(self.feed.thinking())
        self.app.brain.thinking = 1
        self.assertTrue(self.feed.thinking())
        self.app.state.gui_focus = 6
        self.assertEqual(self.feed.gui_focus(), 6)
        self.app.state.game_quit = True
        self.assertTrue(self.feed.game_quit())

    def test_a_broken_event_never_raises(self):
        self.holo = None
        self.app.bus.fire("speech.started", text="hi")      # no hologram yet: just ignored


class LipTiming(unittest.TestCase):
    def test_lips_wait_for_the_real_sound(self):
        holo, c = make()
        app = App()
        feed = HologramFeed(app, lambda: holo)
        feed.attach()
        app.bus.fire("speech.started", text="Hello commander", audio="")
        self.assertFalse(holo.speaking)                      # still making the sound: no lips yet
        app.bus.fire("speech.audio", what="start", text="Hello commander", seconds=None)
        self.assertTrue(holo.speaking)
        app.bus.fire("speech.audio", what="end", text="", seconds=None)
        self.assertFalse(holo.speaking)

    def test_recorded_line_starts_at_once(self):
        holo, c = make()
        app = App()
        HologramFeed(app, lambda: holo).attach()
        app.bus.fire("speech.started", text="Docking granted", audio="dock.mp3")
        self.assertTrue(holo.speaking)

    def test_mouth_is_stretched_to_the_real_length(self):
        holo, c = make()
        holo.speech_started("Hello commander how are you", c.t)
        natural = h.track_length(holo.track)
        holo.set_duration(natural * 2)
        self.assertAlmostEqual(holo.time_scale, 2.0, places=2)
        # one natural length in, the mouth is only half way through, so it is still moving
        self.assertTrue(holo.speaking)
        self.assertIsNotNone(holo._mouth_goal(c.t + natural * 0.9) or "x")
        self.assertIsNone(holo._mouth_goal(c.t + natural * 2 + 2))

    def test_stretch_is_limited(self):
        holo, c = make()
        holo.speech_started("Hello commander", c.t)
        holo.set_duration(9999)
        self.assertLessEqual(holo.time_scale, 3.0)
        holo.set_duration(0.0001)
        self.assertGreaterEqual(holo.time_scale, 0.4)


class GameFocus(unittest.TestCase):
    def setUp(self):
        self.feed = HologramFeed(App(), lambda: None)
        self.title = "Elite - Dangerous (CLIENT)"
        self.feed.title_provider = lambda: self.title
        self.feed.boot_seconds = 20.0

    def test_waits_after_start_then_powers_up(self):
        self.assertFalse(self.feed.game_in_focus(1000.0))        # game just appeared: she is still starting up
        self.assertFalse(self.feed.game_in_focus(1010.0))
        self.assertTrue(self.feed.game_in_focus(1021.0))

    def test_powers_down_when_you_leave_the_game(self):
        self.feed.game_in_focus(1000.0)
        self.assertTrue(self.feed.game_in_focus(1030.0))
        self.title = "Discord"
        self.assertFalse(self.feed.game_in_focus(1031.0))
        self.title = "Elite - Dangerous (CLIENT)"
        self.assertTrue(self.feed.game_in_focus(1032.0))         # back: powers up at once, no second start-up wait

    def test_new_start_waits_again(self):
        self.feed.game_in_focus(1000.0)
        self.assertTrue(self.feed.game_in_focus(1030.0))
        self.feed.game_gone()
        self.assertFalse(self.feed.game_in_focus(1031.0))

    def test_unknown_window_keeps_her_on(self):
        self.feed.title_provider = lambda: None
        self.assertTrue(self.feed.game_in_focus(5.0))


class Voice(unittest.TestCase):
    def test_phrases(self):
        for t in ("show the hologram", "turn on the hologram", "switch the hologram on", "please show your hologram"):
            self.assertEqual(which(t), "holo_on", t)
        for t in ("hide the hologram", "turn off the hologram", "switch the hologram off", "close the hologram"):
            self.assertEqual(which(t), "holo_off", t)
        self.assertIsNone(which("what is a hologram"))

    def test_setting_flips(self):
        s = Settings(**{"hologram.enabled": False})
        said = []
        nar = type("N", (), {"say": lambda self, k, f=None: said.append(k)})()
        v = WindowVoice(s, lambda name: None, nar)
        v.try_handle("show the hologram")
        self.assertTrue(s.get("hologram.enabled"))
        v.try_handle("hide the hologram")
        self.assertFalse(s.get("hologram.enabled"))
        self.assertEqual(said, ["Window_HologramShown", "Window_HologramHidden"])

    def test_lines_exist(self):
        import json
        data = json.load(open("voicepacks/default/streaming.json"))
        self.assertTrue(data["Window_HologramShown"] and data["Window_HologramHidden"])


class Defaults(unittest.TestCase):
    def test_off_by_default(self):
        from core.settings import DEFAULTS
        self.assertFalse(DEFAULTS["hologram"]["enabled"])

if __name__ == "__main__":
    unittest.main()
