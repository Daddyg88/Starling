"""0.75.0: she brings up the hull, a bounty and a long session on her own."""
import unittest
from types import SimpleNamespace

from tests.test_chitchat import Base


class StateRemarkTests(Base):
    def test_healthy_and_clean_means_no_state_remarks(self):
        self.state = SimpleNamespace(docked=False, in_supercruise=False, hull_health=1.0, wanted=False)
        self.assertEqual(self.chat.state_keys(self.state), [])

    def test_damaged_hull_wanted_and_long_session(self):
        self.state = SimpleNamespace(docked=False, in_supercruise=False, hull_health=0.55, wanted=True)
        self.later(3 * 3600)
        keys = self.chat.state_keys(self.state)
        self.assertEqual(set(keys), {"ChitChat_Hull", "ChitChat_Wanted", "ChitChat_Long"})
        values = self.chat.context()
        self.assertEqual(values["hull"], 55)
        self.assertEqual(values["hours"], 3)

    def test_the_hull_line_names_the_real_number(self):
        self.state = SimpleNamespace(docked=False, in_supercruise=False, hull_health=0.42, wanted=False)
        self.later(1000)
        said = []
        for _ in range(12):
            self.later(5000)
            self.chat.state_said.clear()
            text = self.chat._pick_text(self.t[0], "", False)
            said.append(text)
        self.assertTrue(any("42" in (t or "") for t in said), said)
        self.assertFalse(any("{" in (t or "") for t in said))

    def test_same_remark_is_not_repeated_within_twenty_minutes(self):
        self.state = SimpleNamespace(docked=False, in_supercruise=False, hull_health=0.5, wanted=False)
        self.chat.state_said["ChitChat_Hull"] = self.t[0]
        self.assertEqual(self.chat.state_keys(self.state), [])
        self.later(1300)
        self.assertEqual(self.chat.state_keys(self.state), ["ChitChat_Hull"])


if __name__ == "__main__":
    unittest.main()


class ParaphraseTests(unittest.TestCase):
    """Sentences nobody wrote a pattern for must still find the right topic, and unrelated ones must find none."""
    def test_rephrased_questions(self):
        from personality.meaning import load_meaning
        meaning = load_meaning()
        for key, text in (("Brain_Scared", "what are you most afraid of"), ("Brain_Lonely", "does it get lonely being on your own"),
                          ("Brain_Bored", "nothing is happening"), ("Brain_SpaceJoke", "know any funny space jokes"),
                          ("Brain_CheerUp", "i feel rubbish can you help"), ("Brain_Weather", "whats the weather like out there")):
            hit = meaning.best(text)
            self.assertTrue(hit and hit[0] == key, (text, hit))

    def test_commands_and_other_questions_match_nothing(self):
        from personality.meaning import load_meaning
        meaning = load_meaning()
        for text in ("open the cargo scoop", "what is the capital of peru", "set a timer for ten minutes", "my friend is called tom"):
            self.assertIsNone(meaning.best(text), text)
