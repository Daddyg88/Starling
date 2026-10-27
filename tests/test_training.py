"""Voice training: she asks for phrases, learns the player's mishearings, and writes a hearing report."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from control.learning import VoiceLearning
from control.matcher import Matcher, normalise
from core.settings import Settings
from stt.training import VoiceTrainer, load_phrases


class Training(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        folder = Path(self.tmp.name)
        self.settings = Settings(folder / "s.json").load()
        self.learning = VoiceLearning(folder / "l.json")
        self.said = []
        self.now = [0.0]
        self.trainer = VoiceTrainer(["lower the landing gear", "open the galaxy map", "turn on the lights"], self.learning,
                                    lambda key, fields, fallback: self.said.append((key, fields)), self.settings,
                                    report_path=folder / "report.txt", clock=lambda: self.now[0])

    def start(self):
        self.assertEqual(self.trainer.try_handle("teach me your voice"), "training")

    def test_phrases_are_real_safe_commands(self):
        matcher = Matcher()
        phrases = load_phrases()
        self.assertGreaterEqual(len(phrases), 15)
        for phrase in phrases:
            hit = matcher.match(phrase)
            self.assertEqual(hit.how, "exact", phrase)
            self.assertFalse(hit.command.strict, phrase)

    def test_start_phrases(self):
        for text in ("teach me your voice", "voice training", "teach her my voice", "start a hearing test", "learn my accent"):
            self.trainer.index = -1
            self.assertEqual(self.trainer.try_handle(text), "training", text)
        self.assertIsNone(self.trainer.try_handle("lower the landing gear"))

    def test_full_session_learns_close_mishearings_only(self):
        self.start()
        self.assertEqual(self.said[-1][0], "Training_Prompt")
        self.assertTrue(self.trainer.hear("Starling, lower the land gear"))        # close but wrong: learned
        self.assertTrue(self.trainer.hear("open the galaxy map"))                    # right
        self.assertTrue(self.trainer.hear("banana"))                                  # nowhere near: not learned
        self.assertFalse(self.trainer.active())
        self.assertEqual(self.said[-1][0], "Training_Done")
        self.assertEqual((self.said[-1][1]["ok"], self.said[-1][1]["fixed"], self.said[-1][1]["unclear"]), (1, 1, 1))
        self.assertEqual(self.learning.learned("lower land gear"), "lower gear")       # the normalised forms
        self.assertIsNone(self.learning.learned("banana"))
        report = (Path(self.tmp.name) / "report.txt").read_text()
        self.assertIn("lower land gear", report)
        self.assertIn("[unclear]", report)

    def test_skip_cancel_and_timeout(self):
        self.start()
        self.trainer.hear("skip")
        self.assertEqual(self.trainer.rows[-1][2], "skipped")
        self.trainer.hear("stop")
        self.assertFalse(self.trainer.active())
        self.assertEqual(self.said[-1][0], "Training_Cancel")
        self.start()
        self.now[0] = 10_000
        self.assertFalse(self.trainer.hear("open the galaxy map"))
        self.assertFalse(self.trainer.active())
        self.assertEqual(self.said[-1][0], "Training_Expired")

    def test_not_active_means_not_handled(self):
        self.assertFalse(self.trainer.hear("anything"))

    def test_report_on_request_contains_no_game_data(self):
        self.trainer.try_handle("starling hearing report")
        text = (Path(self.tmp.name) / "report.txt").read_text()
        self.assertIn("Starling hearing report", text)
        self.assertNotIn("Commander", text)


from tests.test_brain import RunnerTests as BrainRunnerBase


class InTheRunner(BrainRunnerBase):
    def test_during_training_a_command_phrase_is_an_answer_not_a_command(self):
        class Fake:
            def __init__(self):
                self.heard = []

            def active(self):
                return True

            def hear(self, text):
                self.heard.append(text)
                return True

            def try_handle(self, text):
                return None

        self.stub = None
        runner = self.runner()
        fake = Fake()
        runner.trainer = fake
        self.base.bus.publish("voice.heard", {"text": "lower the landing gear", "wake": False, "command": "", "ptt": False})
        self.assertEqual(fake.heard, ["lower the landing gear"])
        self.assertFalse(self.base.sender.pressed)


if __name__ == "__main__":
    unittest.main()
