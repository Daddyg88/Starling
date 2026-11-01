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


if __name__ == "__main__":
    unittest.main()
