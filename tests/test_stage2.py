"""0.74.0: the address book (people.py) and follow-ups that need the question before (context.py)."""
import tempfile
import unittest
from pathlib import Path

from personality import context
from personality.knowledge import Knowledge
from personality.people import People
from tests.test_brain import Base as BrainBase


class ContextTests(unittest.TestCase):
    def test_pieces_and_rewrites(self):
        self.assertEqual(context.piece_of("and spain"), "spain")
        self.assertEqual(context.piece_of("what about new zealand"), "new zealand")
        self.assertEqual(context.piece_of("no i meant vienna"), "vienna")
        self.assertIsNone(context.piece_of("what about you"))
        self.assertIsNone(context.piece_of("and the other one"))
        self.assertEqual(context.rewrite("what is the capital of france", "spain"), "what is the capital of spain")
        self.assertEqual(context.rewrite("what is 5 times 3", "10"), "what is 10 times 3")
        self.assertIsNone(context.rewrite("hello", "spain"))
        self.assertIsNone(context.rewrite("hello there", "10"))


class PeopleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "people.json"
        self.people = People(self.path)

    def test_learn_recall_forget_and_save(self):
        self.assertEqual(self.people.learn("my friend andrew from germany", "My friend Andrew from Germany"),
                         ("Andrew", "friend", "Germany", True))
        self.assertEqual(self.people.who("who is andrew")[1]["place"], "Germany")
        self.assertEqual(self.people.who("where is andrew from")[0], "where")
        self.assertEqual(People(self.path).who("who is andrew")[0], "who")          # survives a restart
        self.assertEqual(self.people.who("forget andrew"), ("forgot", "Andrew"))
        self.assertIsNone(self.people.who("who is andrew"))

    def test_needs_a_capital_so_feelings_are_not_names(self):
        self.assertIsNone(self.people.learn("my wife is tired", "My wife is tired"))
        self.assertIsNone(self.people.learn("my friend is from germany", "My friend is from Germany"))
        self.assertEqual(self.people.learn("my wife is sarah", "My wife is Sarah")[0], "Sarah")

    def test_forget_everyone(self):
        self.people.learn("tom is my brother", "Tom is my brother")
        self.assertEqual(self.people.who("forget everyone"), ("forgot_all", True))
        self.assertEqual(self.people.items, {})
        self.assertFalse(self.path.exists())


class BrainStage2Tests(BrainBase):
    def setUp(self):
        super().setUp()
        self.tmp2 = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp2.cleanup)
        self.brain.people = People(Path(self.tmp2.name) / "people.json")
        self.brain.knowledge = Knowledge()

    def said(self):
        return str(self.speech.said[-1]["text"])

    def test_she_learns_and_recalls_a_friend(self):
        self.assertTrue(self.ask("My friend Andrew from Germany"))
        self.assertIn("Andrew", self.said())
        self.assertIn("Germany", self.said())
        self.assertTrue(self.ask("who is Andrew"))
        self.assertIn("Germany", self.said())
        self.assertTrue(self.ask("who do you know"))
        self.assertIn("Andrew", self.said())
        self.assertTrue(self.ask("forget Andrew"))
        self.assertEqual(self.brain.people.items, {})

    def test_and_spain_follows_the_capital_question(self):
        self.assertTrue(self.ask("what is the capital of France"))
        self.assertIn("Paris", self.said())
        self.assertTrue(self.ask("and Spain"))
        self.assertIn("Madrid", self.said())
        self.assertTrue(self.ask("no I meant Italy"))
        self.assertIn("Rome", self.said())

    def test_a_follow_up_with_nothing_before_it_is_ignored(self):
        self.assertFalse(self.speech.said)
        self.assertIsNone(self.brain._follow_context("and spain"))
        self.assertFalse(self.speech.said)


if __name__ == "__main__":
    unittest.main()
