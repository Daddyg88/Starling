"""Merit mining: pledged power, Spansh answers (shaped like the real ones), A/B question and plotting."""

import json
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace

from events.registry import load_registry
from journal.game_state import GameState
from mining import merit
from tests.test_ask_and_paint import Rig
from tests.test_brain import Base
from tests.test_mining import SyncThread
from tests.test_sell_route import FakeRoute


def body(system, name, distance, reserve="Pristine", rings=("Metallic", "Rocky"), state="Stronghold"):
    return {"name": name, "system_name": system, "distance": distance, "reserve_level": reserve,
            "rings": [{"type": t, "name": name + " Ring"} for t in rings], "system_controlling_power": "Aisling Duval",
            "system_power_state": state}


def station(name, system, kind, demand, commodity="Platinum", price=56108):
    return {"name": name, "system_name": system, "type": kind,
            "market": [{"commodity": "Gold", "demand": 9999999, "sell_price": 1}, {"commodity": commodity, "demand": demand,
                                                                                   "sell_price": price, "supply": 0, "buy_price": 0}]}


BODIES = {"count": 4, "results": [
    body("HR 5048", "HR 5048 1", 127.8),
    body("HR 5048", "HR 5048 2", 127.8),                       # same system: only counted once
    body("Visto", "Visto A 2", 148.0),
    body("Goibniugo", "Goibniugo 6", 148.2),
    body("Weak", "Weak 1", 150.0, reserve="Low"),              # not pristine
    body("Icy", "Icy 1", 151.0, rings=("Icy",)),               # not metallic
]}
STATIONS = {"count": 4, "results": [
    station("KBV-G9L", "Visto", "Drake-Class Carrier", 4938),                 # a fleet carrier: never
    station("Pharos", "HR 5048", "Dodec Starport", 204166),
    station("Brothers Relay", "HR 5048", "Outpost", 8535),
    station("Small Fry", "Goibniugo", "Outpost", 1500),                       # under 2000
]}


class Parsing(unittest.TestCase):
    def test_bodies_one_per_system_pristine_metallic_only(self):
        found = merit.parse_bodies(BODIES)
        self.assertEqual([b["system"] for b in found], ["HR 5048", "Visto", "Goibniugo"])
        self.assertEqual(found[0]["body"], "HR 5048 1")

    def test_stations_need_2000_demand_and_no_carriers(self):
        best = merit.parse_stations(STATIONS, "Platinum")
        self.assertEqual(list(best), ["HR 5048"])
        self.assertEqual(best["HR 5048"]["station"], "Pharos")            # the hungrier one
        self.assertEqual(best["HR 5048"]["demand"], 204166)

    def test_junk_never_crashes(self):
        for raw in (None, {}, [], {"results": None}, {"results": ["x", 3, {}]}):
            self.assertEqual(merit.parse_bodies(raw), [])
            self.assertEqual(merit.parse_stations(raw, "Platinum"), {})

    def test_requests_ask_for_exactly_the_three_rules(self):
        request = merit.bodies_request("Aisling Duval", "Sol")
        self.assertEqual(request["filters"]["rings"], [{"type": ["Metallic"]}])
        self.assertEqual(request["filters"]["reserve_level"], {"value": ["Pristine"]})
        self.assertEqual(request["filters"]["system_controlling_power"], {"value": ["Aisling Duval"]})
        self.assertEqual(request["reference_system"], "Sol")
        market = merit.stations_request(["A", "B"], "Platinum", "Sol")["filters"]
        self.assertEqual(market["system_name"], {"value": ["A", "B"]})
        self.assertEqual(market["market"][0]["demand"]["value"][0], 2000)


class FakePost:
    def __init__(self, bodies=BODIES, stations=STATIONS, error=None):
        self.bodies, self.stations, self.error, self.calls = bodies, stations, error, []

    def __call__(self, path, body):
        self.calls.append((path, body))
        if self.error:
            raise self.error
        return self.bodies if path.startswith("/bodies") else self.stations


class Finder(unittest.TestCase):
    def make(self, post=None, **values):
        from tests.test_phase6b import make_settings
        return merit.MeritFinder(make_settings(**values), post=post or FakePost(), thread_factory=SyncThread)

    def test_nearest_system_with_ring_and_market(self):
        finder = self.make()
        options, ok = finder.lookup("Sol", "Aisling Duval")
        self.assertTrue(ok)
        self.assertEqual(len(options), 1)
        self.assertEqual((options[0]["system"], options[0]["station"], options[0]["body"]), ("HR 5048", "Pharos", "HR 5048 1"))
        self.assertEqual(options[0]["tons"], 204166)

    def test_every_metal_is_searched_and_the_best_market_wins(self):
        calls = []

        def post(path, body):
            calls.append((path, body))
            if path.startswith("/bodies"):
                return BODIES
            metal = body["filters"]["market"][0]["name"]
            return {"results": [station("Dock", "Visto", "Coriolis Starport", 3000 if metal == "Osmium" else 2100, metal)]}
        finder = self.make(post=post)
        options, _ = finder.lookup("Sol", "Aisling Duval")
        self.assertEqual(options[0]["system"], "Visto")
        self.assertEqual(options[0]["material"], "Osmium")
        self.assertEqual(sorted({c[1]["filters"]["market"][0]["name"] for c in calls if c[0].startswith("/stations")}),
                         ["Osmium", "Painite", "Palladium", "Platinum"])

    def test_cached_for_a_while(self):
        post = FakePost()
        finder = self.make(post=post)
        finder.lookup("Sol", "Aisling Duval")
        n = len(post.calls)
        finder.lookup("Sol", "Aisling Duval")
        self.assertEqual(len(post.calls), n)

    def test_offline_and_no_bodies(self):
        self.assertEqual(self.make(post=FakePost(error=urllib.error.URLError("down"))).lookup("Sol", "X"), ([], False))
        post = FakePost(bodies={"results": []})
        self.assertEqual(self.make(post=post).lookup("Sol", "X"), ([], True))
        self.assertEqual(len(post.calls), 1)               # nothing to look for markets in

    def test_power_from_dashboard_beats_journal(self):
        state = SimpleNamespace(power="Yuri Grom")
        self.assertEqual(self.make().power(state), "Yuri Grom")
        self.assertEqual(self.make(merit__power="Zemina Torval").power(state), "Zemina Torval")
        self.assertEqual(self.make().power(SimpleNamespace(power=None)), "")


class Journal(unittest.TestCase):
    def feed(self, *entries):
        registry, state = load_registry(), GameState()
        for entry in entries:
            registry[entry["event"]].update_state(entry, state)
        return state

    def test_pledged_power_events(self):
        self.assertEqual(self.feed({"event": "Powerplay", "Power": "Aisling Duval"}).power, "Aisling Duval")
        self.assertEqual(self.feed({"event": "PowerplayJoin", "Power": "Yuri Grom"}).power, "Yuri Grom")
        s = self.feed({"event": "Powerplay", "Power": "A"}, {"event": "PowerplayDefect", "FromPower": "A", "ToPower": "B"})
        self.assertEqual(s.power, "B")
        self.assertIsNone(self.feed({"event": "Powerplay", "Power": "A"}, {"event": "PowerplayLeave"}).power)


class BrainFlow(Base):
    def setUp(self):
        super().setUp()
        self.post = FakePost()
        self.brain.merit = merit.MeritFinder(self.settings, post=self.post, thread_factory=SyncThread)
        self.state.power = "Aisling Duval"

    def spoken(self):
        return " ".join(item.get("text", "") if isinstance(item, dict) else str(item) for item in self.speech.said)

    def test_the_sentence_is_understood(self):
        for text in ("I want to go merit mining", "starling i want to go merit mining", "find me somewhere for merit mining",
                     "I want to mine for merits"):
            self.speech.said.clear()
            self.post.calls.clear()
            self.brain.merit = merit.MeritFinder(self.settings, post=self.post, thread_factory=SyncThread)     # no cache
            self.ask(text)
            self.assertTrue(self.post.calls, text)

    def test_one_option_found(self):
        self.ask("i want to go merit mining")
        said = self.spoken()
        for part in ("HR 5048", "Pharos", "204,166", "Platinum"):
            self.assertIn(part, said)
        self.assertEqual(self.post.calls[0][1]["reference_system"], "Sol")
        self.assertEqual(self.post.calls[0][1]["filters"]["system_controlling_power"]["value"], ["Aisling Duval"])

    def test_no_power_known(self):
        self.state.power = None
        self.ask("i want to go merit mining")
        self.assertEqual(self.post.calls, [])
        self.assertIn("Power", self.spoken())

    def test_nothing_found_and_offline(self):
        self.brain.merit = merit.MeritFinder(self.settings, post=FakePost(bodies={"results": []}), thread_factory=SyncThread)
        self.ask("i want to go merit mining")
        self.assertIn("couldn't find", self.spoken())
        self.speech.said.clear()
        self.brain.merit = merit.MeritFinder(self.settings, post=FakePost(error=OSError("x")), thread_factory=SyncThread)
        self.ask("i want to go merit mining")
        self.assertIn("Spansh", self.spoken())

    def test_switched_off(self):
        self.settings.set("mining.merit", False)
        self.ask("i want to go merit mining")
        self.assertEqual(self.post.calls, [])
        self.assertIn("switched off", self.spoken())


OPTIONS = [
    {"station": "Pharos", "system": "HR 5048", "body": "HR 5048 1", "material": "Platinum", "price": 56108, "tons": 204166,
     "distance": 127.8},
    {"station": "Dock", "system": "Visto", "body": "Visto A 2", "material": "Osmium", "price": 40000, "tons": 3000, "distance": 148.0},
]


class AskAB(unittest.TestCase):
    def make(self):
        r = Rig()
        r.route = FakeRoute()
        r.ask.plot_provider = r.route
        return r

    def test_a_or_b_then_the_route_is_plotted(self):
        r = self.make()
        r.ask.offer_sale("", OPTIONS, "best", "merit")
        said = r.speech.said[-1]["text"]
        for part in ("The first one", "The second one", "HR 5048 1", "Pharos", "204,166", "Platinum", "Visto A 2", "Dock", "3,000", "Osmium"):
            self.assertIn(part, said)
        r.finish_question()
        self.assertTrue(r.say("option b"))
        r.finish_question()
        self.assertTrue(r.say("yes please"))
        self.assertEqual(r.route.plotted, ["Visto"])

    def test_one_option_goes_straight_to_the_route_question(self):
        r = self.make()
        r.ask.offer_sale("", OPTIONS[:1], "best", "merit")
        r.finish_question()
        r.say("yes")
        self.assertEqual(r.route.plotted, ["HR 5048"])


class Lines(unittest.TestCase):
    def test_lines_are_clean_and_complete(self):
        data = json.loads(Path("voicepacks/default/merit.json").read_text(encoding="utf-8"))
        banned = ("laugh", "giggle", "chortle", "uploading", "baka", "ug,", "uhh", "gtfo")
        for key in ("Merit_Looking", "Merit_NoPower", "Merit_NoSystem", "Merit_Disabled", "Merit_Offline", "Merit_None",
                    "Merit_Options", "Merit_OneOption"):
            self.assertIn(key, data)
        for key, lines in data.items():
            if key.startswith("_"):
                continue
            self.assertEqual(len(lines), len(set(lines)), key)
            for line in lines:
                self.assertFalse([b for b in banned if b in line.lower()], line)
