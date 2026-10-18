import tempfile
import unittest
from pathlib import Path

from core.event_bus import Event, EventBus
from core.settings import Settings
from personality.manners import Manners, has_thanks, only_thanks
from personality.mood_engine import MoodEngine
from tests.test_dialogue import FakeSpeech, real_dialogue


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


class Setup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bus = EventBus()
        self.settings = Settings(Path(self.tmp.name) / "s.json").load()
        self.dialogue = real_dialogue()
        self.speech = FakeSpeech()
        self.clock = Clock()
        self.mood = MoodEngine(self.bus, self.settings, save_path=Path(self.tmp.name) / "m.json", clock=self.clock,
                               persist=False)
        self.manners = Manners(self.bus, self.speech, self.dialogue, self.settings, mood=self.mood, clock=self.clock)

    def hear(self, text, wake=True):
        self.manners.on_heard(Event(name="voice.heard", data={"wake": wake, "command": text, "text": text}, priority="normal"))


class DetectionTests(unittest.TestCase):
    def test_detects_thanks(self):
        for text in ("thank you", "Thanks Starling", "cheers", "thank you very much"):
            self.assertTrue(has_thanks(text))
            self.assertTrue(only_thanks(text), text)

    def test_thanks_inside_a_request_is_not_only_thanks(self):
        self.assertTrue(has_thanks("open the galaxy map thank you"))
        self.assertFalse(only_thanks("open the galaxy map thank you"))
        self.assertFalse(has_thanks("lower the landing gear"))


class MannersTests(Setup):
    def test_thanks_after_a_request_gives_points_and_a_reply(self):
        self.hear("open the galaxy map")
        before = self.mood.score
        self.hear("thank you")
        self.assertGreater(self.mood.score, before)
        self.assertEqual(len(self.speech.said), 1)
        self.assertNotIn("{", self.speech.said[0]["text"])

    def test_no_thanks_never_costs_points(self):
        before = self.mood.score
        for _ in range(5):
            self.hear("open the galaxy map")
        self.assertEqual(self.mood.score, before)
        self.assertEqual(self.speech.said, [])

    def test_thanks_in_the_same_sentence_counts(self):
        before = self.mood.score
        self.hear("open the galaxy map thank you")
        self.assertGreater(self.mood.score, before)

    def test_one_request_is_thanked_once(self):
        self.hear("open the galaxy map")
        self.hear("thank you")
        score = self.mood.score
        self.hear("thanks")
        self.assertEqual(self.mood.score, score)
        self.assertEqual(len(self.speech.said), 2)       # still polite, no extra points

    def test_late_thanks_gets_a_reply_but_no_points(self):
        self.hear("open the galaxy map")
        self.clock.t += 300
        before = self.mood.score
        self.hear("thank you")
        self.assertEqual(self.mood.score, before)
        self.assertEqual(len(self.speech.said), 1)

    def test_not_addressed_is_ignored(self):
        self.settings.set("stt.require_wake", True)
        self.manners.on_heard(Event(name="voice.heard", data={"text": "thank you"}, priority="normal"))
        self.assertEqual(self.speech.said, [])

    def test_every_mood_has_welcome_lines(self):
        for mood in ("", "Friendly", "Close", "Sarcastic", "Frustrated"):
            self.assertTrue(self.dialogue.pool("YoureWelcome", mood, False, False), mood)


if __name__ == "__main__":
    unittest.main()
