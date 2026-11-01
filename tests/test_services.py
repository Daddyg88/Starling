import json
import unittest
from pathlib import Path
from mining import services
from tests.test_brain import Base
from tests.test_mining import SyncThread
from personality.meaning import Meaning, tokens


class ParseTests(unittest.TestCase):
    def test_skips_carriers_and_wrong_services(self):
        raw = {"results": [{"name": "X", "system_name": "A", "type": "Drake-Class Carrier", "distance": 1},
                           {"name": "Y", "system_name": "B", "type": "Coriolis", "distance": 5.5, "distance_to_arrival": 812.4,
                            "services": [{"name": "Black Market"}]},
                           {"name": "Z", "system_name": "C", "type": "Outpost", "services": [{"name": "Market"}]},
                           {"name": "W", "system_name": "D", "type": "Outpost", "distance": 9, "services": [{"name": "Black Market"}]},
                           "junk"]}
        found = services.parse_stations(raw, "Black Market")
        self.assertEqual([f["station"] for f in found], ["Y", "W"])
        self.assertEqual(found[0]["arrival"], 812)

    def test_bad_reply(self):
        self.assertEqual(services.parse_stations(None, "Black Market"), [])
        self.assertEqual(services.parse_stations({"results": None}, "Black Market"), [])


class FinderTests(unittest.TestCase):
    def finder(self, post):
        class Now:
            t = 0
        return services.ServiceFinder(None, post=post, clock=lambda: Now.t)

    def test_lookup_and_cache(self):
        calls = []

        def post(path, body):
            calls.append(body)
            return {"results": [{"name": "Y", "system_name": "B", "type": "Coriolis"}]}
        finder = self.finder(post)
        self.assertEqual(finder.lookup("Sol")[1], True)
        finder.lookup("Sol")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["reference_system"], "Sol")

    def test_offline(self):
        def post(path, body):
            raise OSError("down")
        self.assertEqual(self.finder(post).lookup("Sol"), ([], False))


class WozLogTests(unittest.TestCase):
    def test_long_repeat_is_ignored(self):
        meaning = Meaning({"Brain_Sleep": ["do you ever sleep", "are you tired"]})
        self.assertIsNone(meaning.best("Go! " * 30))

    def test_ill_is_not_a_health_word(self):
        import json
        from core import paths
        topics = json.loads((paths.CONFIG_DIR / "chat_topics.json").read_text(encoding="utf-8"))["topics"]
        self.assertNotIn("ill", topics["health"])


class BrainFlow(Base):
    def setUp(self):
        super().setUp()
        self.calls = []

        def post(path, body):
            self.calls.append(body)
            return {"results": [{"name": "Hutton Orbital", "system_name": "Alpha Centauri", "type": "Orbis", "distance": 4.4,
                                 "distance_to_arrival": 1500, "services": [{"name": "Black Market"}]}]}
        self.brain.services = services.ServiceFinder(self.settings, post=post, thread_factory=SyncThread)

    def said(self):
        return " ".join(i.get("text", "") if isinstance(i, dict) else str(i) for i in self.speech.said)

    def test_sentences(self):
        for text in ("where is the nearest black market", "starling find me a black market", "any black markets nearby",
                     "closest blackmarket"):
            self.calls.clear()
            self.brain.services = services.ServiceFinder(self.settings, post=lambda p, b: self.calls.append(b) or {"results": []},
                                                         thread_factory=SyncThread)
            self.ask(text)
            self.assertTrue(self.calls, text)

    def test_answer(self):
        self.ask("where is the nearest black market")
        self.assertIn("Hutton Orbital", self.said())
        self.assertIn("Alpha Centauri", self.said())
        self.assertEqual(self.calls[0]["reference_system"], "Sol")

    def test_other_services_ask_for_the_right_thing(self):
        for text, wanted in (("where is the nearest material trader", "Material Trader"), ("find me a tech broker", "Technology Broker"),
                             ("nearest interstellar factors", "Interstellar Factors Contact"),
                             ("where can i find vista genomics", "Vista Genomics"), ("closest shipyard", "Shipyard"),
                             ("nearest outfitting", "Outfitting"), ("find the nearest universal cartographics", "Universal Cartographics")):
            self.calls.clear()
            self.brain.services = services.ServiceFinder(self.settings, post=lambda p, b: self.calls.append(b) or {"results": []},
                                                         thread_factory=SyncThread)
            self.ask(text)
            self.assertTrue(self.calls, text)
            self.assertEqual(self.calls[0]["filters"]["services"][0]["name"], wanted, text)

    def test_not_a_search(self):
        self.ask("what is a black market")
        self.assertEqual(self.calls, [])

    def test_lines_exist(self):
        data = json.loads(Path("voicepacks/default/services.json").read_text(encoding="utf-8"))
        for key in ("Service_Looking", "Service_Found", "Service_None", "Service_Offline", "Service_NoSystem"):
            self.assertIn(key, data)


class OfferRouteTests(unittest.TestCase):
    """After a search she offers 'the first one or the second one', then 'shall I plot a route?'."""

    STATIONS = [{"station": "Hutton Orbital", "system": "Alpha Centauri", "distance": 4.4, "arrival": 1500, "type": "Orbis"},
                {"station": "Dock", "system": "Visto", "distance": 20.0, "arrival": None, "type": "Coriolis"}]

    def make(self):
        from tests.test_ask_and_paint import Rig
        from tests.test_sell_route import FakeRoute
        r = Rig()
        r.route = FakeRoute()
        r.ask.plot_provider = r.route
        return r

    def test_two_options_then_route(self):
        r = self.make()
        r.ask.offer_sale("black market", self.STATIONS, "best", "service")
        said = r.speech.said[-1]["text"]
        for part in ("The first one", "The second one", "Hutton Orbital", "Alpha Centauri", "1,500 light seconds", "Dock", "Visto"):
            self.assertIn(part, said)
        r.finish_question()
        self.assertTrue(r.say("the second one"))
        r.finish_question()
        self.assertTrue(r.say("yes please"))
        self.assertEqual(r.route.plotted, ["Visto"])

    def test_one_option_goes_straight_to_the_route_question(self):
        r = self.make()
        r.ask.offer_sale("material trader", self.STATIONS[:1], "best", "service")
        self.assertIn("material trader", r.speech.said[-1]["text"])
        r.finish_question()
        r.say("yes")
        self.assertEqual(r.route.plotted, ["Alpha Centauri"])

    def test_brain_uses_the_offer(self):
        class Ask:
            calls = []
            def offer_sale(self, material, options, order, mode):
                self.calls.append((material, len(options), mode))
                return "said"
        brain = BrainFlow("test_answer")
        brain.setUp()
        brain.brain.ask = Ask()
        brain.ask("where is the nearest black market")
        self.assertEqual(Ask.calls, [("black market", 1, "service")])


if __name__ == "__main__":
    unittest.main()
