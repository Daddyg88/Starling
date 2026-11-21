"""'Don't forget your didgeridoo, mate': only with the Australian voice, only when the Nomad is recovered, about one time in five."""

import json
import random
import tempfile
import unittest
from pathlib import Path

from core import paths
from core.event_bus import Event
from core.settings import Settings
from personality import speaker as speaker_module
from personality.speaker import EventSpeaker
from tests.test_dialogue import FakeSpeech, real_dialogue
from tts import pronounce


class Rolls:
    """A random generator that gives the numbers it is told to (for the one-in-five roll), then real ones."""
    def __init__(self, *numbers):
        self.numbers = list(numbers)
        self.real = random.Random(1)

    def random(self):
        return self.numbers.pop(0) if self.numbers else self.real.random()

    def choice(self, items):
        return self.real.choice(items)

    def __getattr__(self, name):
        return getattr(self.real, name)


def make(voice, roll):
    settings = Settings(Path(tempfile.gettempdir()) / "nope.json").load()
    settings.set("tts.voice", voice)
    speech = FakeSpeech()
    rules = {"default_cooldown_seconds": 0, "cooldown_seconds": {}, "max_age_seconds": {}}
    dialogue = real_dialogue()
    return EventSpeaker(None, speech, dialogue, settings, rules, rng=Rolls(roll)), speech, dialogue


def lines():
    data = json.loads((paths.VOICEPACKS_DIR / "default" / "aussie.json").read_text(encoding="utf-8"))
    return data["NomadDidgeridoo"]


class DidgeridooTests(unittest.TestCase):
    def test_there_are_plenty_of_lines_and_they_all_say_it(self):
        pool = lines()
        self.assertGreaterEqual(len(pool), 25)
        self.assertEqual(len(set(pool)), len(pool))
        for line in pool:
            self.assertIn("didgeridoo", line.lower())
        self.assertEqual(speaker_module.DIDGERIDOO_CHANCE, 0.2)

    def test_australian_voice_and_a_lucky_roll_gives_the_didgeridoo(self):
        speaker, speech, _ = make("melo_en_au", 0.1)
        speaker.on_event(Event(name="NomadDocked", data={}, priority="low"))
        self.assertIn(speech.said[0]["text"], lines())

    def test_an_unlucky_roll_gives_the_ordinary_line(self):
        speaker, speech, _ = make("melo_en_au", 0.5)
        speaker.on_event(Event(name="NomadDocked", data={}, priority="low"))
        self.assertNotIn("didgeridoo", speech.said[0]["text"].lower())

    def test_other_voices_never_get_it(self):
        for voice in ("kokoro_af_heart", "kokoro_bf_emma", ""):
            speaker, speech, _ = make(voice, 0.0)
            speaker.on_event(Event(name="NomadDocked", data={}, priority="low"))
            self.assertNotIn("didgeridoo", speech.said[0]["text"].lower(), voice)

    def test_only_the_nomad_gets_it(self):
        speaker, speech, _ = make("melo_en_au", 0.0)
        for name in ("DockSRV", "Docked", "LaunchSRV"):
            speaker.on_event(Event(name=name, data={}, priority="low"))
        self.assertTrue(all("didgeridoo" not in s["text"].lower() for s in speech.said))

    def test_about_one_in_five_over_many_recoveries(self):
        settings = Settings(Path(tempfile.gettempdir()) / "nope.json").load()
        settings.set("tts.voice", "melo_en_au")
        speech = FakeSpeech()
        speaker = EventSpeaker(None, speech, real_dialogue(), settings, {"default_cooldown_seconds": 0, "cooldown_seconds": {}, "max_age_seconds": {}},
                               rng=random.Random(7))
        for _ in range(500):
            speaker.on_event(Event(name="NomadDocked", data={}, priority="low"))
        share = sum("didgeridoo" in s["text"].lower() for s in speech.said) / len(speech.said)
        self.assertGreater(share, 0.14)
        self.assertLess(share, 0.27)

    def test_it_is_said_the_way_he_spelt_it(self):
        pronounce.reload()
        said = pronounce.prepare("Don't forget your didgeridoo, mate.", "melo_en_au")
        self.assertIn("dij-uh-ree-doo", said)


if __name__ == "__main__":
    unittest.main()
