"""She says 'the first one / the second one' (never A / B) and understands 1st / 2nd."""
import json, os, unittest
from personality import answers

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Ordinals(unittest.TestCase):
    def test_first(self):
        for t in ("the 1st one please", "the first one please", "first", "1st", "number one", "the first one"):
            self.assertEqual(answers.choose(t), "A", t)

    def test_second(self):
        for t in ("the second one please", "The Second one please", "the 2nd one", "2nd", "second", "number two"):
            self.assertEqual(answers.choose(t), "B", t)

    def test_old_letters_still_work(self):
        self.assertEqual(answers.choose("option a"), "A")
        self.assertEqual(answers.choose("option b"), "B")

    def test_no_spoken_a_or_b(self):
        import re
        for name in ("selling.json", "merit.json"):
            text = open(os.path.join(ROOT, "voicepacks", "default", name), encoding="utf-8").read()
            json.loads(text)
            self.assertIsNone(re.search(r"Option [AB]\b|\bA or B\b", text), name)


if __name__ == "__main__":
    unittest.main()
