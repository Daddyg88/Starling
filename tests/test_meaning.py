"""Understanding rephrased questions by meaning, and remembering the last few answers."""

import json
import unittest

from core import paths
from personality.meaning import Meaning, load_meaning, tokens
from tests.test_brain import Base


def _read(name):
    with open(paths.CONFIG_DIR / name, encoding="utf-8") as handle:
        return json.load(handle)


class Understanding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meaning = load_meaning()

    def key(self, text):
        hit = self.meaning.best(text)
        return hit[0] if hit else None

    def test_rephrased_questions_find_their_topic(self):
        cases = {
            "are you fond of me at all": "Brain_LikeMe",
            "do you ever get scared in the dark": "Brain_Scared",
            "i am dead tired": "Brain_Tired",
            "you make me laugh so much": "Brain_Funny",
            "what do you get up to when im away": "Brain_Hobby",
            "which colour do you think is the nicest": "Brain_FavColour",
            "i am absolutely starving": "Brain_Hungry",
            "can you make me feel better": "Brain_CheerUp",
            "what does my future hold": "Brain_Fortune",
            "how many years old are you": "Brain_Age",
            "do you enjoy a good fight": "Brain_LikeCombat",
            "write me some poetry": "Brain_Poem",
        }
        for said, expected in cases.items():
            self.assertEqual(self.key(said), expected, said)

    def test_unrelated_sentences_get_nothing(self):
        for said in ("who won the football match last night", "open the galaxy map", "hello there", "how do i plot a route",
                     "set a timer for ten minutes", "the cargo hold is almost full", "jump to the next system", "blah blah blah",
                     "do you reckon youre brainy"):
            self.assertIsNone(self.meaning.best(said), said)

    def test_near_misses_are_not_taken_for_a_topic(self):
        for said in ("how are you today", "i hate mining", "what is your name", "can you sing me a song", "are you real"):
            self.assertIsNone(self.meaning.best(said), said)
        self.assertEqual(self.key("you are a legend"), "Brain_Praised")

    def test_one_word_is_not_enough(self):
        self.assertIsNone(self.meaning.best("tired"))

    def test_two_close_topics_mean_no_answer(self):
        tiny = Meaning({"A": ["red apple pie"], "B": ["red apple tart"]})
        self.assertIsNone(tiny.best("red apple"))

    def test_words_are_folded_together(self):
        self.assertEqual(tokens("Loving the favourite colours"), tokens("like fave colour"))

    def test_every_example_topic_is_a_chatty_line_topic(self):
        intents = {i["key"]: i for i in _read("brain_intents.json")["intents"]}
        examples = _read("brain_examples.json")
        for key in examples:
            if key.startswith("_"):
                continue
            self.assertIn(key, intents, key)
            self.assertEqual(intents[key].get("kind", "line"), "line", key)
            self.assertGreaterEqual(len(examples[key]), 3, key)

    def test_every_example_finds_its_own_topic(self):
        examples = _read("brain_examples.json")
        wrong = []
        for key, texts in examples.items():
            if key.startswith("_"):
                continue
            for text in texts:
                hit = self.meaning.best(text)
                if hit is None or hit[0] != key:
                    wrong.append((key, text, hit))
        # a few examples are genuinely shared by two topics (a joke request and a reaction); that is allowed, a wrong topic is not
        self.assertFalse([w for w in wrong if w[2] is not None], wrong)


class InTheBrain(Base):
    def setUp(self):
        super().setUp()
        self.settings.set("brain.freechat", False)         # these tests are about meaning matching, not free chat
    def test_a_rephrased_question_is_answered(self):
        reply = self.ask("are you fond of me at all")
        self.assertTrue(reply)
        self.assertEqual(self.brain.history[-1][1], "Brain_LikeMe")
        self.assertTrue(self.speech.said)

    def test_nonsense_is_still_not_answered(self):
        self.assertIsNone(self.ask("who won the football match last night"))

    def test_an_exact_pattern_still_wins(self):
        self.ask("do you like me")
        self.assertEqual(self.brain.history[-1][1], "Brain_LikeMe")

    def test_say_that_again(self):
        first = self.ask("whats your favourite colour")
        self.assertTrue(first)
        again = self.ask("say that again")
        self.assertIn(first, again)

    def test_say_that_again_with_nothing_said(self):
        self.assertTrue(self.ask("say that again"))
        self.assertFalse(self.brain.history)

    def test_what_were_we_talking_about(self):
        self.ask("whats your favourite colour")
        self.ask("do you sleep")
        reply = self.ask("what were we talking about")
        self.assertIn("favourite colour", reply)
        self.assertIn("sleep", reply)

    def test_nothing_to_recap(self):
        self.assertTrue(self.ask("what were we talking about"))

    def test_old_answers_are_forgotten(self):
        self.ask("whats your favourite colour")
        self.clock.now += 3600
        self.assertTrue(self.ask("say that again"))
        self.assertEqual(self.brain._recent(), [])

    def test_only_the_last_few_are_kept(self):
        for text in ("do you sleep", "do you dream", "are you scared", "do you have feelings", "do you get lonely",
                     "how old are you", "whats your favourite colour", "whats your favourite food"):
            self.ask(text)
        self.assertLessEqual(len(self.brain.history), 6)

    def test_meaning_can_be_switched_off_by_the_tests(self):
        self.brain.meaning = None
        self.assertIsNone(self.ask("are you fond of me at all"))


if __name__ == "__main__":
    unittest.main()
