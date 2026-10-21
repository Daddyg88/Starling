"""Tests: she offers sell options A and B, asks which, then asks to plot a neutron route."""

import unittest

from personality.answers import choose
from tests.test_ask_and_paint import Rig

OPTIONS = [
    {"station": "Smith Port", "system": "Wregoe JU-E c25-18", "price": 310000, "demand": 5000, "distance": 12.0, "pad": "large"},
    {"station": "Big Dock", "system": "Alpha", "price": 250000, "demand": 2500, "distance": 40.0, "pad": "large"},
]


class FakeRoute:
    """Stands in for core.app.plot_system_by_macro: remembers which system names it was asked to paste."""
    def __init__(self, on=True):
        self.on, self.plotted = on, []

    def __call__(self, system):
        if not self.on:
            return False, "voice commands are not running"
        self.plotted.append(system)
        return True, ""


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


class MacroTargetTests(unittest.TestCase):
    def test_the_macro_pastes_the_chosen_system_not_a_route_waypoint(self):
        from types import SimpleNamespace
        from navigation.voice import RouteVoice
        copied = []
        follower = SimpleNamespace(active=False, copier=lambda text: copied.append(text) or True)
        voice = RouteVoice(follower, None, SimpleNamespace(say=lambda *a, **k: None), SimpleNamespace(get=lambda k, d=None: d),
                           lambda: None)
        voice.set_target("Wregoe JU-E c25-18")
        self.assertEqual(voice.prepare_plot(), (True, ""))
        self.assertEqual(copied, ["Wregoe JU-E c25-18"])         # exact spelling, no route needed
        self.assertEqual(voice.prepare_plot()[0], False)         # used once: next time there is no route
        self.assertEqual(copied, ["Wregoe JU-E c25-18"])


class SellFlowTests(unittest.TestCase):
    def make(self, route=None):
        r = Rig()
        r.route = route or FakeRoute()
        r.ask.plot_provider = r.route
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

    def test_macro_unavailable_is_explained(self):
        r = self.make(FakeRoute(on=False))
        r.ask.offer_sale("Platinum", OPTIONS[:1])
        r.finish_question()
        r.say("yes")
        self.assertEqual(r.route.plotted, [])
        self.assertIn("voice commands are not running", r.speech.said[-1]["text"])

    def test_when_she_cannot_hear_she_only_tells_you(self):
        r = self.make()
        r.listening = False
        r.ask.offer_sale("Platinum", OPTIONS)
        self.assertIsNone(r.ask.pending)
        self.assertIn("Smith Port", r.speech.said[-1]["text"])

    def test_nearest_options_are_spoken_with_the_distance(self):
        r = self.make()
        r.ask.offer_sale("Platinum", OPTIONS, "nearest", "sell")
        said = r.speech.said[-1]["text"]
        self.assertIn("12 light years", said)
        self.assertIn("40 light years", said)

    def test_buying_gets_the_same_a_or_b_and_route_offer(self):
        r = self.make()
        buy = [{"station": "Shop One", "system": "Sol", "price": 100, "stock": 700, "tons": 700, "distance": 2.0},
               {"station": "Shop Two", "system": "Alpha", "price": 120, "stock": 300, "tons": 300, "distance": 9.0}]
        r.ask.offer_sale("Tritium", buy, "best", "buy")
        said = r.speech.said[-1]["text"]
        for part in ("Shop One", "700", "Shop Two", "300"):
            self.assertIn(part, said)
        r.finish_question()
        r.say("b")
        r.finish_question()
        r.say("yes")
        self.assertEqual(r.route.plotted, ["Alpha"])

    def test_the_questions_are_understood(self):
        from personality.brain import Brain
        import json
        from core import paths
        intents = json.load(open(paths.CONFIG_DIR / "brain_intents.json", encoding="utf-8"))["intents"]
        import re
        def kind(sentence):
            for item in intents:
                if any(re.search(p, sentence) for p in item["patterns"]):
                    return item.get("kind", "line")
        for sentence in ("where can i sell this platinum for the best price", "where is the nearest place to sell this",
                         "where is the closest place to sell this platinum", "where can i sell this near here"):
            self.assertEqual(kind(sentence), "sellprice", sentence)
        for sentence in ("where can i buy tritium", "where is the nearest place to buy tritium", "where can i buy tritium nearby",
                         "where is the cheapest place to buy tritium"):
            self.assertEqual(kind(sentence), "buyprice", sentence)
        self.assertEqual(Brain._order("where is the nearest place to sell this"), "nearest")
        self.assertEqual(Brain._order("where can i sell this for the best price"), "best")

    def test_the_lines_have_variety(self):
        from personality.dialogue import DialogueManager
        from core import paths
        d = DialogueManager(paths.VOICEPACKS_DIR / "default").load()
        for key, minimum in (("Sell_Options", 6), ("Sell_WhichOne", 6), ("Sell_RouteAsk", 6), ("Sell_RouteYes", 6), ("Sell_RouteNo", 5), ("Sell_NearOptions", 5), ("Buy_Options", 5), ("Buy_NearOptions", 4)):
            self.assertGreaterEqual(len(d.lines.get(key, [])), minimum, key)


if __name__ == "__main__":
    unittest.main()
