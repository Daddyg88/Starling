import tempfile
import unittest
from pathlib import Path

from control.learning import VoiceLearning
from control.matcher import Matcher


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "learn.json"
        self.learning = VoiceLearning(self.path)
        self.matcher = Matcher(learning=self.learning)

    def tearDown(self):
        self.tmp.cleanup()

    def close_miss(self):
        """A sentence that is close to a real one but not exact."""
        for sentence in sorted(self.matcher.index, key=len, reverse=True):
            command = self.matcher.index[sentence][0]
            if len(sentence) > 14 and not command.strict:
                mangled = sentence[:-1] + ("x" if sentence[-1] != "x" else "y")
                if mangled not in self.matcher.index:
                    match = self.matcher.match(mangled)
                    if match and match.score < 1:
                        return mangled, match.phrase
        self.fail("no close miss found")

    def test_a_repeated_mishearing_becomes_exact(self):
        heard, sentence = self.close_miss()
        self.assertIsNone(self.learning.learned(heard))
        self.matcher.match(heard)                 # second time she understands it the same way
        self.assertEqual(self.learning.learned(heard), sentence)
        hit = self.matcher.match(heard)
        self.assertEqual(hit.score, 1.0)
        self.assertEqual(hit.phrase, sentence)

    def test_it_survives_a_restart(self):
        heard, sentence = self.close_miss()
        self.matcher.match(heard)
        again = VoiceLearning(self.path)
        self.assertEqual(again.learned(heard), sentence)
        self.assertEqual(again.count(), 1)

    def test_switched_off_learns_nothing(self):
        learning = VoiceLearning(Path(self.tmp.name) / "off.json", enabled=lambda: False)
        matcher = Matcher(learning=learning)
        heard, _ = self.close_miss()
        matcher.match(heard)
        matcher.match(heard)
        self.assertEqual(learning.seen, {})

    def test_ambiguous_mishearing_is_not_trusted(self):
        self.learning.seen["blah blah"] = {"lower gear": 2, "raise gear": 2}
        self.assertIsNone(self.learning.learned("blah blah"))

    def test_corrupt_file_is_survivable(self):
        self.path.write_text("{not json")
        self.assertEqual(VoiceLearning(self.path).seen, {})

    def test_forget_all(self):
        heard, _ = self.close_miss()
        self.matcher.match(heard)
        self.learning.forget_all()
        self.assertIsNone(self.learning.learned(heard))


class SafetyTests(unittest.TestCase):
    def test_weak_matches_are_not_learned(self):
        m = Matcher(learning=VoiceLearning(Path(tempfile.mkdtemp()) / "l.json"))
        hit = m.match("close the fss overlay")        # a real mis-match from a user's log: close to galnet, but not it
        if hit is not None and hit.score < 0.90:
            m.match("close the fss overlay")
            self.assertEqual(m.learning.seen, {})

    def test_new_overlay_words_and_close_all(self):
        m = Matcher()
        for said, command in (("close all overlays", "vc_hide_all"), ("show gallonet overlay", "vc_galnet_ticker"),
                              ("close colonisation overlay", "vc_colony_needs")):
            hit = m.match(said)
            self.assertIsNotNone(hit, said)
            self.assertEqual(hit.command.id, command, said)
