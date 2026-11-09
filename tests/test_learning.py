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


class TeachingTests(unittest.TestCase):
    """0.89.2: sentences she missed are kept, and 'I meant ...' teaches her at once."""

    def setUp(self):
        from tests import test_macros
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.t = test_macros.MacroTests()
        self.runner = self.t.build()
        self.learning = VoiceLearning(Path(self.tmp.name) / "learn.json")
        self.runner.matcher.learning = self.learning
        self.now = [100.0]
        self.runner.clock = lambda: self.now[0]
        from control.teach import TeachHelper
        self.helper = TeachHelper(lambda: self.runner, clock=lambda: self.now[0])
        self.runner.extra_helpers.append(self.helper)

    def test_a_missed_sentence_is_kept_and_listed(self):
        self.runner.run_text("blorp zanzibar")
        self.assertIn("blorp zanzibar", self.learning.misses)
        self.assertEqual(self.learning.last_miss[0], "blorp zanzibar")
        self.assertIn("blorp zanzibar", self.helper.try_handle("what did you miss"))

    def test_nothing_missed_says_so(self):
        self.assertIn("haven't missed", self.helper.try_handle("what did you not catch"))

    def test_long_chat_sentences_are_not_kept(self):
        self.learning.note_miss("tell me all about the history of the empire and its many fine ships")
        self.assertEqual(self.learning.misses, {})

    def test_i_meant_teaches_her_at_once(self):
        command = next(s for s in sorted(self.runner.matcher.index, key=len) if len(s) > 8 and not self.runner.matcher.index[s][0].strict)
        self.runner.run_text("blorp zanzibar")
        reply = self.helper.try_handle("I meant " + command)
        self.assertIn("Got it", reply)
        self.assertEqual(self.learning.learned("blorp zanzibar"), command)
        self.assertNotIn("blorp zanzibar", self.learning.misses)
        self.assertEqual(self.runner.matcher.match("blorp zanzibar").phrase, command)       # understood exactly from now on

    def test_i_meant_without_a_recent_miss_is_left_alone(self):
        self.assertIsNone(self.helper.try_handle("I meant lower the landing gear"))
        self.learning.note_miss("blorp zanzibar", now=self.now[0])
        self.now[0] += 400
        self.assertIsNone(self.helper.try_handle("I meant lower the landing gear"))

    def test_it_must_be_a_real_command(self):
        self.runner.run_text("blorp zanzibar")
        self.assertIn("don't know", self.helper.try_handle("I meant fly to the moon on a spoon"))
        self.assertIsNone(self.learning.learned("blorp zanzibar"))

    def test_big_actions_are_never_taught(self):
        strict = next(s for s in self.runner.matcher.index if self.runner.matcher.index[s][0].strict)
        self.runner.run_text("blorp zanzibar")
        self.assertIn("don't know", self.helper.try_handle("I meant " + strict))
        self.assertIsNone(self.learning.learned("blorp zanzibar"))

    def test_misses_survive_a_restart(self):
        self.learning.note_miss("blorp zanzibar")
        again = VoiceLearning(Path(self.tmp.name) / "learn.json")
        self.assertIn("blorp zanzibar", again.misses)
