import json
import random
import unittest
import urllib.error
from types import SimpleNamespace

from core import paths
from mining import minerals, prices
from mining.tracker import MiningTracker
from personality import line_keys
from personality.chitchat import ChitChat
from tests.helpers import make_processor
from tests.test_brain import Base


def ev(name, **data):
    return SimpleNamespace(name=name, data=data)


PROSPECT_PLATINUM = {"event": "ProspectedAsteroid", "Materials": [
    {"Name": "Platinum", "Name_Localised": "Platinum", "Proportion": 23.4},
    {"Name": "Bertrandite", "Name_Localised": "Bertrandite", "Proportion": 30.0}],
    "Content": "$AsteroidMaterialContent_High;", "Content_Localised": "Material Content: High", "Remaining": 100.0}


class MineralTests(unittest.TestCase):
    def test_tiers(self):
        self.assertEqual(minerals.tier("Platinum"), "top")
        self.assertEqual(minerals.tier("$lowtemperaturediamond_name;"), "top")
        self.assertEqual(minerals.tier("Low Temperature Diamonds"), "top")
        self.assertEqual(minerals.tier("Opal"), "top")
        self.assertEqual(minerals.tier("Osmium"), "good")
        self.assertEqual(minerals.tier("Gold"), "low")
        self.assertEqual(minerals.tier("Silver"), "low")
        self.assertEqual(minerals.tier("Bertrandite"), "low")
        self.assertEqual(minerals.tier(None), "low")

    def test_speech_to_game_name(self):
        self.assertEqual(minerals.from_speech("where do i sell the void opals"), "opal")
        self.assertEqual(minerals.from_speech("best price for ltds"), "lowtemperaturediamond")
        self.assertEqual(minerals.from_speech("where should i sell platinum"), "platinum")
        self.assertIsNone(minerals.from_speech("where should i sell this"))


class EventTests(unittest.TestCase):
    def feed(self, entry):
        processor, _bus, heard = make_processor()
        processor.handle_line(json.dumps(entry))
        return heard[-1]

    def test_top_mineral_is_announced_with_percent(self):
        event = self.feed(PROSPECT_PLATINUM)
        self.assertEqual(event.data["Announce"], "top")
        self.assertEqual(event.data["Material"], "Platinum")
        self.assertEqual(event.data["Percent"], "23")
        self.assertEqual(line_keys.keys_for(event), ["Prospected_Top"])

    def test_motherlode(self):
        entry = dict(PROSPECT_PLATINUM, MotherlodeMaterial="Painite", MotherlodeMaterial_Localised="Painite")
        event = self.feed(entry)
        self.assertTrue(event.data["Motherlode"])
        self.assertEqual(line_keys.keys_for(event), ["Prospected_Motherlode"])
        self.assertEqual(event.data["Material"], "Painite")

    def test_good_needs_enough_of_it_and_poor_rocks_are_brief(self):
        small = {"event": "ProspectedAsteroid", "Materials": [{"Name": "Osmium", "Proportion": 4.0}], "Content_Localised": "Material Content: Medium"}
        self.assertEqual(self.feed(small).data["Announce"], "")
        big = {"event": "ProspectedAsteroid", "Materials": [{"Name": "Osmium", "Proportion": 14.0}], "Content_Localised": "Material Content: Medium"}
        self.assertEqual(self.feed(big).data["Announce"], "good")
        poor = {"event": "ProspectedAsteroid", "Materials": [{"Name": "Bertrandite", "Proportion": 14.0}], "Content_Localised": "Material Content: Low"}
        self.assertEqual(line_keys.keys_for(self.feed(poor)), ["Prospected_Poor"])

    def test_damaged_prospect_entries_do_not_crash(self):
        for entry in ({"event": "ProspectedAsteroid"}, {"event": "ProspectedAsteroid", "Materials": "x"},
                      {"event": "ProspectedAsteroid", "Materials": [None, {"Name": None, "Proportion": "abc"}]}):
            self.feed(entry)

    def test_refined_is_not_called_out_every_time(self):
        processor, _bus, heard = make_processor()
        said = []
        for _ in range(12):
            processor.handle_line(json.dumps({"event": "MiningRefined", "Type": "$platinum_name;", "Type_Localised": "Platinum"}))
            said.append(heard[-1].data["Announce"])
        self.assertEqual(said[0], "first")
        self.assertEqual(said[4], "milestone")                  # every 5th tonne (normal chattiness)
        self.assertEqual(said[9], "milestone")
        self.assertEqual(line_keys.keys_for(heard[0]), ["Refined_First"])
        self.assertLess(sum(1 for x in said if x), 8)
        low = self.feed({"event": "MiningRefined", "Type": "bertrandite", "Type_Localised": "Bertrandite"})
        self.assertEqual(line_keys.keys_for(low), [])

    def test_gold_and_silver_are_ignored_entirely(self):
        for kind in ("Gold", "Silver"):
            event = self.feed({"event": "MiningRefined", "Type": kind.lower(), "Type_Localised": kind})
            self.assertEqual(event.data["Tier"], "low")
            self.assertEqual(line_keys.keys_for(event), [])

    def test_depleted_and_nearly_dry(self):
        gone = self.feed({"event": "ProspectedAsteroid", "Materials": [], "Content_Localised": "Material Content: Low", "Remaining": 0.0})
        self.assertEqual(line_keys.keys_for(gone), ["Prospected_Depleted"])
        dry = self.feed({"event": "ProspectedAsteroid", "Materials": [], "Content_Localised": "Material Content: Low", "Remaining": 9.0})
        self.assertEqual(line_keys.keys_for(dry), ["Prospected_Dry"])
        fresh = self.feed(dict(PROSPECT_PLATINUM, Remaining=100.0))
        self.assertEqual(line_keys.keys_for(fresh), ["Prospected_Top"])

    def test_shopping_events(self):
        event = self.feed({"event": "ShipyardBuy", "ShipType": "python", "ShipPrice": 56978000})
        self.assertEqual(event.data["ship"], "Python")
        self.assertEqual(event.data["Price"], "56,978,000")
        mod = self.feed({"event": "ModuleBuy", "BuyItem": "int_cargorack_size5_class1", "BuyItem_Localised": "Cargo Rack", "BuyPrice": 100})
        self.assertEqual(mod.data["module"], "Cargo Rack")
        self.assertIn(line_keys.keys_for(self.feed({"event": "LaunchDrone", "Type": "Prospector"})), ([], ["Launch_Prospector"]))   # spoken only some of the time


class TrackerTests(unittest.TestCase):
    def test_counts_and_best(self):
        tracker = MiningTracker()
        for kind, tier in (("bertrandite", "low"), ("platinum", "top"), ("platinum", "top"), ("gold", "good")):
            tracker.on_event(ev("MiningRefined", Commodity=kind, Material=kind, Tier=tier))
        tracker.on_event(ev("ProspectedAsteroid", Motherlode=True))
        tracker.on_event(ev("AsteroidCracked"))
        self.assertEqual(tracker.total(), 4)
        self.assertEqual(tracker.best(), ("platinum", 2))
        self.assertEqual(tracker.to_sell(), "platinum")
        self.assertEqual((tracker.prospected, tracker.motherlodes, tracker.cracked), (1, 1, 1))
        self.assertIn("2 tonnes of Platinum", tracker.best_text())

    def test_new_session_after_a_long_gap(self):
        now = [0.0]
        tracker = MiningTracker(clock=lambda: now[0])
        tracker.on_event(ev("MiningRefined", Commodity="gold", Material="Gold"))
        now[0] = 4 * 3600
        tracker.on_event(ev("AsteroidCracked"))
        self.assertEqual(tracker.total(), 0)


ARDENT = [
    {"stationName": "Fleet Thing", "stationType": "FleetCarrier", "systemName": "Far", "sellPrice": 900000, "maxLandingPadSize": 3},
    {"stationName": "Smith Port", "stationType": "Coriolis", "systemName": "Sol", "sellPrice": 310000, "demand": 5000, "maxLandingPadSize": 3, "distance": 12.4},
    {"stationName": "Big Dock", "stationType": "Orbis", "systemName": "Alpha", "sellPrice": 250000, "demand": 2500, "maxLandingPadSize": 3},
    {"stationName": "Low Outpost", "stationType": "Outpost", "systemName": "Beta", "sellPrice": 260000, "demand": 9000, "maxLandingPadSize": 2},
    {"stationName": "Hungry Little", "stationType": "Coriolis", "systemName": "Gamma", "sellPrice": 290000, "demand": 400, "maxLandingPadSize": 3},
    {"stationName": "Broken"}, "junk", {"stationName": "X", "systemName": "Y", "sellPrice": "lots"},
]


class PriceTests(unittest.TestCase):
    def test_parse_orders_by_price_and_skips_carriers_and_junk(self):
        results = prices.parse(ARDENT)
        self.assertEqual([r["station"] for r in results], ["Smith Port", "Big Dock"])
        self.assertEqual(results[0]["pad"], "large")
        self.assertEqual(prices.parse("nonsense"), [])
        self.assertEqual(prices.parse({"results": ARDENT})[0]["price"], 310000)

    def test_sell_search_is_1000ly_one_day_1000_tons(self):
        url = prices.build_url("Sol", "platinum")
        for part in ("maxDistance=1000", "maxDaysAgo=1", "minVolume=1000"):
            self.assertIn(part, url)
        buy = prices.build_url("Sol", "tritium", mode="buy")
        self.assertIn("maxDistance=100", buy)
        self.assertIn("/exports?", buy)

    def test_url_is_safe(self):
        url = prices.build_url("Sol & Co", "lowtemperaturediamond")
        self.assertIn("/system/name/Sol%20%26%20Co/commodity/name/lowtemperaturediamond/nearby/imports?", url)
        self.assertIn("fleetCarriers=false", url)

    def test_cache_and_offline(self):
        calls = []
        now = [0.0]

        def fetch(url):
            calls.append(url)
            return ARDENT
        finder = prices.PriceFinder(fetch=fetch, clock=lambda: now[0])
        self.assertTrue(finder.lookup("Sol", "platinum")[1])
        finder.lookup("Sol", "platinum")
        self.assertEqual(len(calls), 1)
        now[0] = 16 * 60
        finder.lookup("Sol", "platinum")
        self.assertEqual(len(calls), 2)

        def offline(url):
            raise urllib.error.URLError("no internet")
        results, ok = prices.PriceFinder(fetch=offline).lookup("Sol", "gold")
        self.assertEqual((results, ok), ([], False))


class SyncThread:
    def __init__(self, target):
        self.target = target

    def start(self):
        self.target()


class BrainMiningTests(Base):
    def setUp(self):
        super().setUp()
        self.tracker = MiningTracker()
        self.fetched = []
        self.finder = prices.PriceFinder(self.settings, fetch=self._fetch, thread_factory=SyncThread)
        self.brain.mining, self.brain.prices = self.tracker, self.finder
        self.reply = ARDENT

    def _fetch(self, url):
        self.fetched.append(url)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply

    def spoken(self):
        return [item.get("text", "") if isinstance(item, dict) else str(item) for item in self.speech.said]

    def test_where_to_sell_named_mineral(self):
        self.ask("where should i sell the platinum")
        self.assertIn("/commodity/name/platinum/", self.fetched[0])
        self.assertIn("/system/name/Sol/", self.fetched[0])
        said = " ".join(self.spoken())
        self.assertIn("Smith Port", said)
        self.assertIn("310,000", said)
        self.assertIn("Big Dock", said)
        self.assertNotIn("Low Outpost", said)          # medium pad: not offered
        self.assertNotIn("Hungry Little", said)        # only wants 400 tons: not offered

    def test_nearest_sorts_by_distance_and_relaxes_demand(self):
        self.reply = [
            {"stationName": "Far Rich", "systemName": "Far", "sellPrice": 400000, "demand": 5000, "maxLandingPadSize": 3, "distance": 300},
            {"stationName": "Close Small", "systemName": "Near", "sellPrice": 200000, "demand": 150, "maxLandingPadSize": 3, "distance": 5},
            {"stationName": "Close Medium", "systemName": "Near", "sellPrice": 900000, "demand": 5000, "maxLandingPadSize": 2, "distance": 1},
        ]
        self.ask("where is the nearest place to sell this platinum")
        self.assertIn("minVolume=100", self.fetched[0])
        said = " ".join(self.spoken())
        self.assertLess(said.index("Close Small"), said.index("Far Rich"))
        self.assertNotIn("Close Medium", said)
        self.fetched.clear()
        self.ask("where can i sell this platinum for the best price")
        self.assertIn("minVolume=1000", self.fetched[0])

    def test_nearest_buy_uses_distance_best_buy_uses_price(self):
        self.reply = [
            {"stationName": "Cheap Far", "systemName": "Far", "buyPrice": 100, "stock": 500, "distance": 90},
            {"stationName": "Dear Near", "systemName": "Near", "buyPrice": 500, "stock": 500, "distance": 3},
        ]
        self.ask("where is the nearest place to buy tritium")
        said = " ".join(self.spoken())
        self.assertLess(said.index("Dear Near"), said.index("Cheap Far"))
        self.speech.said.clear()
        self.finder._cache.clear()
        self.ask("where can i buy tritium")
        said = " ".join(self.spoken())
        self.assertLess(said.index("Cheap Far"), said.index("Dear Near"))

    def test_uses_what_you_mined_when_no_name_is_given(self):
        self.tracker.on_event(ev("MiningRefined", Commodity="painite", Material="Painite"))
        self.ask("where should i sell this")
        self.assertIn("/commodity/name/painite/", self.fetched[0])

    def test_nothing_known_asks_which(self):
        self.ask("where should i sell this")
        self.assertEqual(self.fetched, [])
        self.assertTrue(self.speech.said)

    def test_offline_and_switched_off_and_empty(self):
        self.reply = urllib.error.URLError("x")
        self.ask("where should i sell the gold")
        self.assertTrue(len(self.speech.said) >= 2)
        self.settings.set("mining.prices", False)
        before = len(self.fetched)
        self.ask("best price for gold")
        self.assertEqual(len(self.fetched), before)

    def test_what_have_we_mined(self):
        self.assertIsNotNone(self.ask("what have we mined"))
        self.tracker.on_event(ev("MiningRefined", Commodity="platinum", Material="Platinum"))
        self.ask("what have we mined")
        self.assertIn("Platinum", " ".join(self.spoken()))


class PackTests(unittest.TestCase):
    def test_combat_target_lines_only_ask_about_wanted_ships(self):
        pack = json.load(open(paths.VOICEPACKS_DIR / "default" / "combat.json", encoding="utf-8"))

        def texts(key):
            return [(x["text"] if isinstance(x, dict) else x) for x in pack.get(key, [])]
        for key in pack:
            if key.startswith("ShipTargeted_Ship") or key.startswith("CombatModeOn"):
                for line in texts(key):
                    self.assertNotIn("get them", line.lower(), key)
                    self.assertNotIn("hunt", line.lower(), key)
        for line in texts("ShipTargeted_Wanted") + texts("ShipTargeted_Bounty"):
            self.assertIn("get them", line.lower())

    def test_every_mining_and_shopping_line_has_values_it_can_be_given(self):
        values = {"Material": "Platinum", "Percent": "20", "ship": "Python", "module": "Cargo Rack", "Price": "1", "Station": "S",
                  "Where": "in X", "Count": 5, "Total": 25, "Stock": "9", "Price2": "2", "Station2": "T", "Where2": "in Y", "total": 3, "best_text": "x"}
        for name in ("mining.json", "shopping.json"):
            pack = json.load(open(paths.VOICEPACKS_DIR / "default" / name, encoding="utf-8"))
            for key, lines in pack.items():
                seen = set()
                for item in lines:
                    text = item["text"] if isinstance(item, dict) else item
                    self.assertNotIn(text, seen, key)
                    seen.add(text)
                    text.format(**values)


class BuyAndFavouriteTests(BrainMiningTests):
    def test_where_to_buy(self):
        self.reply = [{"stationName": "Seller Port", "systemName": "Sol", "buyPrice": 50, "stock": 900, "maxLandingPadSize": 3},
                      {"stationName": "Empty", "systemName": "Sol", "buyPrice": 10, "stock": 0},
                      {"stationName": "Dearer", "systemName": "Alpha", "buyPrice": 80, "stock": 10}]
        self.ask("where can i buy some liquid oxygen")
        self.assertIn("/commodity/name/liquidoxygen/nearby/exports", self.fetched[0])
        said = " ".join(self.spoken())
        self.assertIn("Seller Port", said)
        self.assertNotIn("Empty", said)

    def test_buy_parse_orders_cheapest_first_and_needs_stock(self):
        rows = prices.parse([{"stationName": "A", "systemName": "S", "buyPrice": 90, "stock": 5},
                             {"stationName": "B", "systemName": "S", "buyPrice": 40, "stock": 5},
                             {"stationName": "C", "systemName": "S", "buyPrice": 1, "stock": 0}], mode="buy")
        self.assertEqual([r["station"] for r in rows], ["B", "A"])

    def test_selling_still_prefers_the_highest_price(self):
        self.ask("where should i sell the platinum")
        self.assertIn("/nearby/imports", self.fetched[0])

    def test_sell_questions_are_not_taken_for_buy_questions(self):
        self.ask("where can i get rid of the platinum")
        self.assertIn("/nearby/imports", self.fetched[0])

    def test_the_ten_boxes_decide_what_excites_her(self):
        self.settings.set("mining.fav1", "gold")
        minerals.bind(self.settings)
        self.addCleanup(minerals.bind, None)
        self.assertEqual(minerals.tier("gold"), "top")
        self.assertEqual(minerals.tier("painite"), "top")
        for n in range(1, 11):
            self.settings.set("mining.fav%d" % n, "")
        self.assertEqual(minerals.tier("platinum"), "low")
        self.assertEqual(minerals.tier("osmium"), "good")

    def test_the_mining_page_has_ten_boxes(self):
        from ui.settings_model import build_pages
        page = next(p for p in build_pages() if p.id == "mining")
        self.assertEqual(len([f for f in page.fields if f.key.startswith("mining.fav")]), 10)


class ChitChatMiningTests(unittest.TestCase):
    def test_mining_talk_while_mining(self):
        from core.event_bus import EventBus
        from core.settings import Settings
        import tempfile
        from pathlib import Path
        bus = EventBus()
        now = [100.0]
        with tempfile.TemporaryDirectory() as tmp:
            settings = Settings(Path(tmp) / "s.json").load()
            chat = ChitChat(bus, None, None, settings, state_provider=lambda: SimpleNamespace(docked=False, in_supercruise=False),
                            clock=lambda: now[0])
            self.assertNotEqual(chat.candidate_keys(), ["ChitChat_Mining"])
            chat.on_event(ev("MiningRefined"))
            self.assertEqual(chat.candidate_keys(), ["ChitChat_Mining"])
            now[0] += 700
            self.assertNotEqual(chat.candidate_keys(), ["ChitChat_Mining"])


if __name__ == "__main__":
    unittest.main()


class MoreMiningSpeechTests(unittest.TestCase):
    def test_pools_are_big_enough_and_files_valid(self):
        from personality.dialogue import DialogueManager
        d = DialogueManager(paths.VOICEPACKS_DIR / "default").load()
        for key, minimum in (("Prospected_Good", 20), ("Prospected_Poor", 26), ("Prospected_Depleted", 18), ("Prospected_Dry", 15),
                             ("Refined_Cheer", 16), ("Refined_Total", 15), ("Refined_Plain", 10), ("Launch_Prospector", 6),
                             ("Launch_Collector", 6), ("ChitChat_Mining", 60)):
            self.assertGreaterEqual(len(d.lines.get(key, [])), minimum, key)

    def test_recent_memory_grows_with_the_pool(self):
        from personality.dialogue import DialogueManager
        d = DialogueManager(paths.VOICEPACKS_DIR / "default").load()
        seen = [d.pick("ChitChat_Mining", "", False, False).text for _ in range(20)]
        self.assertGreaterEqual(len(set(seen)), 17)               # a 60+ line pool does not repeat inside 20 picks

    def test_ordinary_minerals_and_good_ones_sometimes_get_a_remark(self):
        from events.mining_events import MiningRefined
        import random
        event = MiningRefined()
        event.rng = random.Random(3)
        said = set()
        for _ in range(400):
            said.add(event.handle({"Type": "iron", "Type_Localised": "Iron"})["Announce"])
        self.assertIn("plain", said)
        self.assertIn("total", said)

    def test_limpet_launches_get_an_occasional_remark(self):
        from events.mining_events import LaunchDrone
        import random
        event = LaunchDrone()
        event.rng = random.Random(5)
        spoken = [event.handle({"Type": "Prospector"}).get("Announce") for _ in range(100)]
        self.assertTrue(0 < sum(1 for s in spoken if s) < 70)
        make = lambda data: SimpleNamespace(name="LaunchDrone", data=data, priority="low")
        self.assertEqual(line_keys.keys_for(make({"Announce": "prospector"})), ["Launch_Prospector"])
        self.assertEqual(line_keys.keys_for(make({})), [])
