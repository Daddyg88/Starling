"""0.77.0: the offline ship database (personality/ships_info.py) and the small fixes from the 0.76.1 log."""
import unittest

from personality.lookup import subject_of
from personality.ships_info import ShipInfo, say_credits, say_number
from tests.test_brain import Base as BrainBase


class ShipInfoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.info = ShipInfo()

    def text(self, question, **kw):
        found = self.info.answer(question, **kw)
        return found[0] if found else None

    def test_all_ships_loaded(self):
        self.assertTrue(self.info.available())
        self.assertEqual(len(self.info.ships), 49)

    def test_numbers_are_spoken_simply(self):
        self.assertEqual(say_credits(128965694), "about 129 million credits")
        self.assertEqual(say_credits(44800), "44,800 credits")
        self.assertEqual(say_number(9.66), "9.7")
        self.assertEqual(say_number(470.0), "470")

    def test_hardpoints_and_cost(self):
        self.assertIn("8 hardpoints", self.text("how many hardpoints does the anaconda have"))
        self.assertIn("129 million", self.text("how much does the anaconda cost"))

    def test_mark_names_and_mass(self):
        self.assertIn("150 tonnes", self.text("what is the mass of the cobra mark 5"))
        self.assertIn("Anaconda Mark 2", self.text("how big is the cargo of the anaconda mark 2"))

    def test_misheard_names(self):
        self.assertIn("Anaconda", self.info.answer("how far can the arconda jump")[1])
        self.assertEqual(self.info.answer("how much cargo can the amaconda carry")[1], "Anaconda")

    def test_ambiguous_ship_asks_which(self):
        self.assertIn("Which one", self.text("what are the hardpoints on the krait"))

    def test_biggest_cargo_and_cheapest(self):
        self.assertIn("Panther Clipper", self.text("which ship has the biggest cargo"))
        self.assertIn("Sidewinder", self.text("what is the cheapest ship"))

    def test_count(self):
        self.assertIn("49", self.text("how many ships are there in elite"))

    def test_animals_are_not_ships_without_a_hint(self):
        self.assertIsNone(self.info.answer("how fast is a dolphin"))
        self.assertIsNotNone(self.info.answer("how fast is the dolphin ship"))

    def test_follow_up_and_my_ship(self):
        self.assertIn("Python", self.text("and its cost", last="Python"))
        self.assertIn("9.7", self.text("what is my ship jump range", current="Anaconda"))
        self.assertIsNone(self.info.answer("what is the capital of peru"))

    def test_every_ship_can_be_summarised(self):
        for ship in self.info.ships:
            found = self.info.answer("tell me about the %s ship" % ship["name"])
            self.assertTrue(found and found[1] == ship["name"], ship["name"])


class BrainShipTests(BrainBase):
    def setUp(self):
        super().setUp()
        self.brain.ships = ShipInfo()

    def said(self):
        return str(self.speech.said[-1]["text"])

    def test_she_answers_and_remembers_the_ship(self):
        self.assertTrue(self.ask("how many hardpoints does the anaconda have"))
        self.assertIn("hardpoints", self.said())
        self.clock.now += 20
        self.assertTrue(self.ask("and its cost"))
        self.assertIn("million", self.said())

    def test_how_many_ships_is_not_the_viewers_chat(self):
        self.assertTrue(self.ask("how many ships are there in elite"))
        self.assertIn("49", self.said())


class LogFixTests(unittest.TestCase):
    def test_empty_subject_is_not_looked_up(self):
        self.assertIsNone(subject_of("tell me about the"))


if __name__ == "__main__":
    unittest.main()
