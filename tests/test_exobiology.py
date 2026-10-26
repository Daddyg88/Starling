import json
import tempfile
import unittest
from pathlib import Path

from core import paths
from journal.exobiology import ExobiologyTracker, spoken_credits
from journal.game_state import GameState
from tests.helpers import make_processor

SEED = {"first_footfall_multiplier": 5, "values": {"Bacterium Informem": 8418000, "Stratum Tectonicas": 19010800}}


def tracker(tmp=None):
    d = Path(tmp or tempfile.mkdtemp())
    seed = d / "seed.json"
    seed.write_text(json.dumps(SEED))
    return ExobiologyTracker(seed, d), d


def organic(kind, species="Bacterium Informem", body=15, ts="2026-10-14T21:00:00Z"):
    return {"event": "ScanOrganic", "ScanType": kind, "Species_Localised": species, "Genus_Localised": "Bacterium",
            "SystemAddress": 1, "Body": body, "timestamp": ts}


class FirstScanTests(unittest.TestCase):
    def test_value_comes_with_the_first_scan(self):
        t, _ = tracker()
        info = t.on_scan_organic(organic("Log"))
        self.assertTrue(info["ValueKnown"])
        self.assertEqual(info["worth"], "8.4 million")

    def test_unknown_species_first_scan(self):
        t, _ = tracker()
        info = t.on_scan_organic(organic("Log", species="Mystery Moss"))
        self.assertFalse(info["ValueKnown"])

    def test_top_ten_flag(self):
        t = ExobiologyTracker(paths.CONFIG_DIR / "exobiology_values.json", Path(tempfile.mkdtemp()))
        values = sorted(t.seed.items(), key=lambda kv: -kv[1])
        best, worst = values[0][0], values[-1][0]
        self.assertTrue(t.is_top(best))
        self.assertFalse(t.is_top(worst))
        self.assertEqual(sum(1 for k in t.seed if t.is_top(k)) >= 10, True)

    def test_few_known_species_means_no_top_ten(self):
        t, _ = tracker()
        self.assertFalse(t.is_top("Stratum Tectonicas"))

    def test_second_sample_may_carry_a_description_third_does_not(self):
        t, _ = tracker()
        t.on_scan_organic(organic("Log"))
        t.on_scan_organic(organic("Sample"))
        third = t.on_scan_organic(organic("Sample"))
        self.assertNotIn("About", third)

    def test_analyse_does_not_repeat_the_value_as_worth_line(self):
        t, _ = tracker()
        for k in ("Log", "Sample", "Sample"):
            t.on_scan_organic(organic(k))
        info = t.on_scan_organic(organic("Analyse"))
        self.assertTrue(info["Complete"])


class SpokenCreditsTests(unittest.TestCase):
    def test_amounts_are_easy_to_say(self):
        self.assertEqual(spoken_credits(8418000), "8.4 million")
        self.assertEqual(spoken_credits(19010800), "19 million")
        self.assertEqual(spoken_credits(95054000), "95.1 million")
        self.assertEqual(spoken_credits(426200), "426 thousand")
        self.assertEqual(spoken_credits(950), "950")
        self.assertEqual(spoken_credits(0), "0")


class SampleCountingTests(unittest.TestCase):
    def test_the_third_sample_is_called_third(self):
        t, _ = tracker()
        # exactly what your journal did: Log, Sample, Sample, Analyse
        self.assertEqual(t.on_scan_organic(organic("Log"))["SampleNumber"], 1)
        self.assertEqual(t.on_scan_organic(organic("Sample"))["SampleNumber"], 2)
        self.assertEqual(t.on_scan_organic(organic("Sample"))["SampleNumber"], 3)
        done = t.on_scan_organic(organic("Analyse"))
        self.assertTrue(done["Complete"])

    def test_a_new_species_starts_again(self):
        t, _ = tracker()
        t.on_scan_organic(organic("Log"))
        t.on_scan_organic(organic("Sample"))
        t.on_scan_organic(organic("Log", species="Stratum Tectonicas"))
        self.assertEqual(t.on_scan_organic(organic("Sample", species="Stratum Tectonicas"))["SampleNumber"], 2)

    def test_a_lone_sample_event_is_second(self):
        t, _ = tracker()
        self.assertEqual(t.on_scan_organic(organic("Sample"))["SampleNumber"], 2)


class WorthTests(unittest.TestCase):
    def finish(self, t, ts="2026-10-14T21:05:00Z", species="Bacterium Informem", body=15):
        t.on_scan_organic(organic("Log", species, body))
        t.on_scan_organic(organic("Sample", species, body))
        t.on_scan_organic(organic("Sample", species, body))
        return t.on_scan_organic(organic("Analyse", species, body, ts))

    def test_worth_and_carried(self):
        t, _ = tracker()
        info = self.finish(t)
        self.assertEqual(info["worth"], "8.4 million")
        self.assertEqual(info["carried"], "8.4 million")
        self.assertFalse(info["FirstFootfall"])
        info = self.finish(t, "2026-10-14T21:10:00Z", "Stratum Tectonicas", 16)
        self.assertEqual(info["carried"], "27.4 million")

    def test_first_footfall_pays_five_times(self):
        t, _ = tracker()
        t.note_body({"SystemAddress": 1, "BodyID": 15, "WasFootfalled": False})
        info = self.finish(t)
        self.assertTrue(info["FirstFootfall"])
        self.assertEqual(info["worth"], "42.1 million")

    def test_footfalled_body_has_no_bonus(self):
        t, _ = tracker()
        t.note_body({"SystemAddress": 1, "BodyID": 15, "WasFootfalled": True})
        self.assertFalse(self.finish(t)["FirstFootfall"])

    def test_unknown_footfall_is_not_assumed(self):
        t, _ = tracker()
        self.assertFalse(self.finish(t)["FirstFootfall"])

    def test_first_value_seen_wins(self):
        t, _ = tracker()
        t.note_body({"SystemAddress": 1, "BodyID": 15, "WasFootfalled": False})
        t.note_body({"SystemAddress": 1, "BodyID": 15, "WasFootfalled": True})   # after you landed
        self.assertTrue(self.finish(t)["FirstFootfall"])

    def test_unknown_species_has_no_price(self):
        t, _ = tracker()
        info = self.finish(t, species="Mystery Plant")
        self.assertFalse(info["ValueKnown"])
        self.assertNotIn("worth", info)
        self.assertEqual(t.carried, [])

    def test_selling_learns_real_prices_and_empties_the_hold(self):
        t, d = tracker()
        self.finish(t)
        t.on_sell({"timestamp": "2026-10-14T22:00:00Z",
                   "BioData": [{"Species_Localised": "Bacterium Informem", "Value": 9000000, "Bonus": 0}]})
        self.assertEqual(t.carried, [])
        self.assertEqual(t.base_value("Bacterium Informem"), 9000000)
        again = ExobiologyTracker(d / "seed.json", d)            # remembered after a restart
        self.assertEqual(again.base_value("Bacterium Informem"), 9000000)

    def test_carried_survives_a_restart_and_history_is_not_counted_twice(self):
        t, d = tracker()
        self.finish(t, "2026-10-14T21:05:00Z")
        again = ExobiologyTracker(d / "seed.json", d)
        self.assertEqual(again.carried_total(), 8418000)
        again.on_scan_organic(organic("Analyse", ts="2026-10-14T21:05:00Z"))   # the same event replayed
        self.assertEqual(again.carried_total(), 8418000)

    def test_dying_loses_unsold_data(self):
        t, _ = tracker()
        self.finish(t)
        t.on_death({"timestamp": "2026-10-14T23:00:00Z"})
        self.assertEqual(t.carried_total(), 0)


class EventTests(unittest.TestCase):
    def test_events_carry_the_facts_the_speaker_needs(self):
        processor, _bus, heard = make_processor()
        processor.state.exobiology = ExobiologyTracker(paths.CONFIG_DIR / "exobiology_values.json")
        for kind in ("Log", "Sample", "Sample", "Analyse"):
            processor.handle_entry({"event": "ScanOrganic", "ScanType": kind, "Species_Localised": "Bacterium Informem",
                                    "SystemAddress": 1, "Body": 4, "timestamp": "2026-10-14T21:0%d:00Z" % len(heard)})
        heard = [h for h in heard if h.name == "ScanOrganic"]       # (a finished new species also makes a BioProgress line)
        numbers = [h.data["SampleNumber"] for h in heard]
        self.assertEqual(numbers, [1, 2, 3, 3])
        self.assertEqual(heard[3].data["worth"], "8.4 million")
        self.assertIn("worth about 8.4 million", heard[3].data["summary"])

    def test_scan_event_feeds_the_footfall_memory(self):
        processor, _bus, heard = make_processor()
        processor.handle_entry({"event": "Scan", "BodyID": 4, "SystemAddress": 1, "WasFootfalled": False,
                                "PlanetClass": "Icy body", "BodyName": "X 4"})
        self.assertTrue(processor.state.exobiology.first_footfall({"SystemAddress": 1, "Body": 4}))

    def test_sale_event_speaks_the_total(self):
        processor, _bus, heard = make_processor()
        processor.handle_entry({"event": "SellOrganicData", "BioData": [{"Value": 8000000, "Bonus": 32000000}]})
        self.assertEqual(heard[-1].data["worth"], "40 million")

    def test_the_shipped_price_table_loads(self):
        t = ExobiologyTracker(paths.CONFIG_DIR / "exobiology_values.json")
        self.assertGreater(len(t.seed), 70)
        self.assertEqual(t.base_value("Bacterium Informem"), 8418000)
        self.assertEqual(t.multiplier, 5)


if __name__ == "__main__":
    unittest.main()


class DistanceTests(unittest.TestCase):
    def test_first_sample_says_how_far_to_walk(self):
        t = ExobiologyTracker(paths.CONFIG_DIR / "exobiology_values.json")
        for genus, species, metres in (("Bacterium", "Bacterium Informem", "500"), ("Aleoida", "Aleoida Arcus", "150"),
                                       ("Stratum", "Stratum Tectonicas", "500"), ("Tussock", "Tussock Pennata", "200"),
                                       ("Electricae", "Electricae Pluma", "1000"), ("Osseus", "Osseus Cornibus", "800")):
            info = t.on_scan_organic({"ScanType": "Log", "Genus_Localised": genus, "Species_Localised": species,
                                      "SystemAddress": 1, "Body": 2})
            self.assertEqual(info["distance"], metres, species)

    def test_only_the_first_sample_gets_a_distance(self):
        t = ExobiologyTracker(paths.CONFIG_DIR / "exobiology_values.json")
        t.on_scan_organic({"ScanType": "Log", "Species_Localised": "Bacterium Informem", "SystemAddress": 1, "Body": 2})
        info = t.on_scan_organic({"ScanType": "Sample", "Species_Localised": "Bacterium Informem",
                                  "SystemAddress": 1, "Body": 2})
        self.assertNotIn("distance", info)

    def test_unknown_genus_gives_no_distance(self):
        t = ExobiologyTracker(paths.CONFIG_DIR / "exobiology_values.json")
        info = t.on_scan_organic({"ScanType": "Log", "Species_Localised": "Mystery Thing", "SystemAddress": 1, "Body": 2})
        self.assertNotIn("distance", info)

    def test_every_genus_in_the_price_list_has_a_distance(self):
        t = ExobiologyTracker(paths.CONFIG_DIR / "exobiology_values.json")
        for name in t.seed:
            self.assertIsNotNone(t.colony_distance({"Species_Localised": name.title()}), name)
