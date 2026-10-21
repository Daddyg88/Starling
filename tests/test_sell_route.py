"""Tests: she offers sell options A and B, asks which, then asks to plot a neutron route."""

import unittest

from personality.answers import choose
from tests.test_ask_and_paint import Rig

OPTIONS = [
    {"station": "Smith Port", "system": "Wregoe JU-E c25-18", "price": 310000, "demand": 5000, "distance": 12.0, "pad": "large"},
    {"station": "Big Dock", "system": "Alpha", "price": 250000, "demand": 2500, "distance": 40.0, "pad": "large"},
]


class FakeRoute:
    def __init__(self, on=True):
        self.on, self.plotted = on, []

    def enabled(self):
        return self.on

    def plot_exact(self, name):
        self.plotted.append(name)


class ChooseTests(unittest.TestCase):
    def test_a_and_b_in_many_spoken_forms(self):
        for text in ("a", "option a", "the first one", "alpha", "yes", "either"):
            self.assertEqual(choose(text), "A", text)
        for text in ("b", "option b", "bee", "the second one", "bravo", "number two"):
            self.assertEqual(choose(text), "B", text)
        for text in ("neither", "no thanks", "never mind", "no"):
            self.assertEqual(choose(text), "no", text)
        self.assertIsNone(choose("what is the weather"))
        self.assertIsNone(choose(""))


class SellFlowTests(unittest.TestCase):
    def make(self, route=None):
        r = Rig()
        r.route = route or FakeRoute()
        r.ask.route_provider = lambda: r.route
        return r

    def test_she_says_both_options_with_price_tons_and_station_then_asks_which(self):
        r = self.make()
        r.ask.offer_sale("Platinum", OPTIONS)
        said = r.speech.said[-1]["text"]
        self.assertEqual(r.speech.said[-1]["event_name"], "ask.question")
        for part in ("310,000", "5,000", "Smith Port", "250,000", "2,500", "Big Dock"):
            self.assertIn(part, said)

    def test_a_then_yes_plots_the_route_to_that_exact_system(self):
        r = self.make()
        r.ask.offer_sale("Platinum", OPTIONS)
        r.finish_question()
        self.assertTrue(r.say("option a"))
        asked = r.speech.said[-1]["text"]
        self.assertIn("route", asked.lower())
        r.finish_question()
        self.assertTrue(r.say("yes please"))
        self.assertEqual(r.route.plotted, ["Wregoe JU-E c25-18"])

    def test_b_picks_the_second_place(self):
        r = self.make()
        r.ask.offer_sale("Platinum", OPTIONS)
        r.finish_question()
        r.say("b")
        r.finish_question()
        r.say("yes")
        self.assertEqual(r.route.plotted, ["Alpha"])

    def test_no_to_the_route_plots_nothing(self):
        r = self.make()
        r.ask.offer_sale("Platinum", OPTIONS)
        r.finish_question()
        r.say("a")
        r.finish_question()
        r.say("no thanks")
        self.assertEqual(r.route.plotted, [])

    def test_neither_ends_it_and_silence_costs_no_mood(self):
        r = self.make()
        r.ask.offer_sale("Platinum", OPTIONS)
        r.finish_question()
        r.say("neither")
        self.assertIsNone(r.ask.pending)
        r2 = self.make()
        r2.ask.offer_sale("Platinum", OPTIONS)
        r2.finish_question()
        before = r2.mood.score
        r2.expire_answer_window()
        self.assertEqual(r2.mood.score, before)
        self.assertEqual(r2.route.plotted, [])

    def test_one_option_goes_straight_to_the_route_question(self):
        r = self.make()
        r.ask.offer_sale("Platinum", OPTIONS[:1])
        r.finish_question()
        r.say("yes")
        self.assertEqual(r.route.plotted, ["Wregoe JU-E c25-18"])

    def test_plotter_switched_off_is_explained(self):
        r = self.make(FakeRoute(on=False))
        r.ask.offer_sale("Platinum", OPTIONS[:1])
        r.finish_question()
        r.say("yes")
        self.assertEqual(r.route.plotted, [])
        self.assertIn("plotter", r.speech.said[-1]["text"].lower())

    def test_when_she_cannot_hear_she_only_tells_you(self):
        r = self.make()
        r.listening = False
        r.ask.offer_sale("Platinum", OPTIONS)
        self.assertIsNone(r.ask.pending)
        self.assertIn("Smith Port", r.speech.said[-1]["text"])

    def test_the_lines_have_variety(self):
        from personality.dialogue import DialogueManager
        from core import paths
        d = DialogueManager(paths.VOICEPACKS_DIR / "default").load()
        for key, minimum in (("Sell_Options", 6), ("Sell_WhichOne", 6), ("Sell_RouteAsk", 6), ("Sell_RouteYes", 6), ("Sell_RouteNo", 5)):
            self.assertGreaterEqual(len(d.lines.get(key, [])), minimum, key)


if __name__ == "__main__":
    unittest.main()
