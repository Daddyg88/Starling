"""0.73.0: she repeats herself less, the unanswered list, the spoken-lines log."""
import json
import tempfile
import unittest
from pathlib import Path

from personality.unanswered import ASK, Unanswered
from tests.test_brain import Base as BrainBase
from tests.test_dialogue import real_dialogue
from tests.test_memory import Base as MemoryBase


class MoreLinesTests(unittest.TestCase):
    def test_more_json_is_valid_and_widens_the_pools(self):
        path = Path(__file__).resolve().parent.parent / "voicepacks" / "default" / "more.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        dialogue = real_dialogue()
        for key, lines in data.items():
            if key.startswith("_"):
                continue
            self.assertIsInstance(lines, list, key)
            texts = {line.text for line in dialogue.lines.get(key, [])}
            for line in lines:
                self.assertIn(line if isinstance(line, str) else line.get("text"), texts, key)
        self.assertGreaterEqual(len(dialogue.lines["ScanOrganic_Log"]), 8)


class RestPeriodTests(MemoryBase):
    def test_recently_mentioned_memory_is_left_out(self):
        first = self.store.add("death", "died at A")
        self.store.add("death", "died at B")
        self.store.mentioned(first)
        names = [m["summary"] for m in self.store.least_mentioned(["death"], limit=5, rest_hours=6)]
        self.assertEqual(names, ["died at B"])
        self.assertEqual(len(self.store.least_mentioned(["death"], limit=5)), 2)


class UnansweredTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "u.json"

    def test_counts_saves_and_ranks(self):
        u = Unanswered(self.path)
        u.add("How tall is Everest?")
        u.add("how tall is everest?")
        u.add("Why is the sky blue?")
        u.add("hi")                                   # too short to be a question
        self.assertEqual(u.top(2), ["how tall is everest?", "why is the sky blue?"])
        self.assertEqual(Unanswered(self.path).top(1), ["how tall is everest?"])
        u.clear()
        self.assertEqual(u.top(), [])
        self.assertFalse(self.path.exists())

    def test_bad_file_starts_empty(self):
        self.path.write_text("{nope", encoding="utf-8")
        self.assertEqual(Unanswered(self.path).top(), [])

    def test_voice_question_pattern(self):
        for text in ("what couldn't you answer", "what questions couldn't you answer", "what do you not know"):
            self.assertTrue(ASK.search(text), text)
        self.assertFalse(ASK.search("what is the time"))


class BrainUnansweredTests(BrainBase):
    def test_she_reads_out_the_list(self):
        self.brain.unanswered = Unanswered(Path(self.tmp.name) / "u.json")
        self.assertTrue(self.ask("what couldn't you answer"))
        self.assertTrue(self.speech.said)
        self.brain.unanswered.add("how tall is everest")
        self.speech.said.clear()
        self.assertTrue(self.ask("what couldn't you answer"))
        self.assertIn("how tall is everest", str(self.speech.said))


if __name__ == "__main__":
    unittest.main()
