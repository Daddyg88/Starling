import json
import tempfile
import unittest
from pathlib import Path

from core.event_bus import EventBus
from events.registry import load_registry
from journal.bio_predict import BioCodex, BioPredictor, load_rules, short_body
from journal.game_state import GameState
from journal.processor import EventProcessor

G = 9.80665


def planet(name, cls="Rocky body", atm="CarbonDioxide", atmosphere="thin Carbon dioxide atmosphere", g=0.2, k=185, volc="", body_id=5, **extra):
    entry = {"event": "Scan", "BodyName": name, "BodyID": body_id, "PlanetClass": cls, "AtmosphereType": atm,
             "Atmosphere": atmosphere, "SurfaceGravity": g * G, "SurfaceTemperature": k, "Volcanism": volc,
             "DistanceFromArrivalLS": 500}
    entry.update(extra)
    return entry


def fss(name, bio=1, geo=0, body_id=5):
    signals = []
    if bio:
        signals.append({"Type": "$SAA_SignalType_Biological;", "Type_Localised": "Biological", "Count": bio})
    if geo:
        signals.append({"Type": "$SAA_SignalType_Geological;", "Type_Localised": "Geological", "Count": geo})
    return {"event": "FSSBodySignals", "BodyName": name, "BodyID": body_id, "Signals": signals}


def run(entries, settings=None):
    bus, got = EventBus(), []
    bus.subscribe("*", lambda e: got.append((e.name, e.data)))
    state = GameState()
    state.system = "Test"
    state.bio = BioPredictor(codex=BioCodex(), settings=settings)
    state.bio.set_system("Test")
    proc = EventProcessor(bus, {}, state, load_registry())
    for e in entries:
        proc.handle_entry(e)
    return got, state


class Rules(unittest.TestCase):
    def test_every_species_has_a_price(self):
        p = BioPredictor()
        missing = [r["n"] for r in load_rules() if not p.species_value(r)]
        self.assertEqual(missing, [])

    def test_short_name(self):
        self.assertEqual(short_body("Synuefe AB-C d1 A 3", "Synuefe AB-C d1"), "A 3")


class Fitting(unittest.TestCase):
    def names(self, entry, geo=0):
        _, state = run([entry, fss(entry["BodyName"], 1, geo)])
        return {r["n"] for r in state.bio.bodies[entry["BodyName"]].candidates}

    def test_cold_co2_rocky(self):
        names = self.names(planet("Test A 1", k=177))
        self.assertIn("Tussock Albata", names)
        self.assertIn("Aleoida Arcus", names)
        self.assertNotIn("Tussock Pennata", names)          # needs 145-155 K
        self.assertNotIn("Stratum Tectonicas", names)       # needs a metal world
        self.assertNotIn("Bacterium Volu", names)           # needs oxygen

    def test_gravity_limits_most_genera(self):
        names = self.names(planet("Test A 1", g=0.4, k=177))
        self.assertFalse({"Tussock Albata", "Aleoida Arcus"} & names)

    def test_stratum_on_warm_sulphur_dioxide(self):
        names = self.names(planet("Test A 1", atm="SulphurDioxide", atmosphere="thin Sulphur dioxide atmosphere", k=300, g=0.5))
        self.assertIn("Stratum Araneamus", names)

    def test_airless_volcanic(self):
        names = self.names(planet("Test A 1", atm="None", atmosphere="", k=250, volc="minor silicate vapour geysers volcanism"))
        self.assertIn("Bark Mounds", names)
        self.assertIn("Albidum Sinuous Tubers", names)
        no_volcano = self.names(planet("Test A 2", atm="None", atmosphere="", k=250, body_id=6))
        self.assertNotIn("Bark Mounds", no_volcano)

    def test_geological_signal_needed_for_fumerola(self):
        warm = planet("Test A 1", cls="Icy body", atm="Methane", atmosphere="thin Methane atmosphere", k=100, volc="minor carbon dioxide geysers volcanism")
        self.assertIn("Fumerola Carbosis", self.names(warm, geo=1))
        self.assertNotIn("Fumerola Carbosis", self.names(warm, geo=0))


class Speaking(unittest.TestCase):
    def test_guess_then_refined(self):
        got, state = run([planet("Test A 1", k=177), fss("Test A 1", 2)])
        names = [n for n, _ in got]
        self.assertIn("BioGuess", names)
        self.assertNotIn("FSSBodySignals", names)           # the guess replaces the plain line
        guess = dict(got)["BioGuess"]
        self.assertEqual(guess["Body"], "A 1")
        self.assertIn("two biological signals", guess["Signals"])
        self.assertTrue(guess["Worth"])

    def test_refined_right_and_wrong(self):
        base = [planet("Test A 1", k=177), fss("Test A 1", 1)]
        saa = lambda genus: {"event": "SAASignalsFound", "BodyName": "Test A 1", "BodyID": 5,
                             "Signals": [{"Type_Localised": "Biological", "Count": 1}],
                             "Genuses": [{"Genus_Localised": genus}]}
        got, _ = run(base + [saa("Tussock")])
        self.assertTrue(dict(got)["BioRefined"]["Right"])
        got, state = run(base + [saa("Brain Tree")])
        data = dict(got)["BioRefined"]
        self.assertFalse(data["Right"])
        self.assertEqual(data["Found"], "Brain Tree")
        self.assertTrue(state.bio.rows()[0]["genera"] == ["Brain Tree"])

    def test_top_hint_for_stratum_tectonicas(self):
        got, _ = run([planet("Test A 1", cls="High metal content body", atm="SulphurDioxide",
                             atmosphere="thin Sulphur dioxide atmosphere", g=0.4, k=300), fss("Test A 1", 1)])
        hints = [d for n, d in got if n == "BioTopHint"]
        self.assertTrue(hints)
        self.assertEqual(hints[0]["Species"], "Stratum Tectonicas")

    def test_switches(self):
        class S:
            def get(self, key, default=None):
                return False if key == "exobiology.guess" else default
        got, _ = run([planet("Test A 1", k=177), fss("Test A 1", 1)], settings=S())
        self.assertNotIn("BioGuess", [n for n, _ in got])

    def test_real_journal_order_signals_first_then_scan(self):
        # in real journals FSSBodySignals comes ONE LINE BEFORE the body's Scan: the guess waits for the scan
        got, state = run([fss("Test A 1", 2)])
        names = [n for n, _ in got]
        self.assertNotIn("BioGuess", names)
        self.assertNotIn("FSSBodySignals", names)           # the plain line stays quiet: the guess follows
        got, state = run([fss("Test A 1", 2), planet("Test A 1", k=177)])
        guess = dict(got)["BioGuess"]
        self.assertEqual(guess["Body"], "A 1")
        self.assertFalse(guess.get("Unknown"))
        self.assertEqual(len([n for n, _ in got if n == "BioGuess"]), 1)
        self.assertEqual(state.bio.rows()[0]["count"], 2)

    def test_forgets_when_leaving(self):
        _, state = run([planet("Test A 1", k=177), fss("Test A 1", 1),
                        {"event": "FSDJump", "StarSystem": "Elsewhere", "JumpDist": 5, "FuelUsed": 1, "FuelLevel": 10, "StarClass": "K"}])
        self.assertEqual(state.bio.bodies, {})
        self.assertEqual(state.bio.props, {})

    def test_limit_per_system(self):
        entries = []
        for i in range(8):
            entries += [planet("Test A %d" % i, k=177, body_id=i), fss("Test A %d" % i, 1, body_id=i)]
        got, _ = run(entries)
        self.assertEqual(len([n for n, _ in got if n == "BioGuess"]), 5)


class Codex(unittest.TestCase):
    def test_codex_and_flags(self):
        got, state = run([{"event": "CodexEntry", "Name_Localised": "Tussock Albata - Lime", "IsNewEntry": True},
                          planet("Test A 1", k=177), fss("Test A 1", 1)])
        self.assertTrue(state.bio.codex.has("Tussock Albata"))
        row = state.bio.rows()[0]
        self.assertEqual(row["new"], 1)                     # other species could still be new

    def test_species_found_updates_row(self):
        _, state = run([planet("Test A 1", k=177), fss("Test A 1", 1),
                        {"event": "ScanOrganic", "ScanType": "Log", "Species_Localised": "Tussock Albata",
                         "Genus_Localised": "Tussock", "SystemAddress": 1, "Body": 5, "timestamp": "2026-01-01T00:00:00Z"}])
        row = state.bio.rows()[0]
        self.assertEqual(row["species"], ["Tussock Albata"])
        self.assertEqual(row["new"], 1)
        state.bio.codex.add("Tussock Albata")
        self.assertEqual(state.bio.rows()[0]["new"], 0)

    def test_history_scan(self):
        folder = Path(tempfile.mkdtemp())
        (folder / "Journal.2026-01-01T000000.01.log").write_text(
            json.dumps({"event": "CodexEntry", "Name_Localised": "Aleoida Arcus - Green"}) + "\n" +
            json.dumps({"event": "ScanOrganic", "ScanType": "Analyse", "Species_Localised": "Stratum Frigus"}) + "\n" +
            json.dumps({"event": "CodexEntry", "Name_Localised": "Albulum Bell Mollusc"}) + "\n")
        data = Path(tempfile.mkdtemp())
        codex = BioCodex(data / "c.json")
        codex.scan_history(folder)
        self.assertEqual(codex.known, {"aleoida arcus", "stratum frigus"})
        again = BioCodex(data / "c.json")
        self.assertTrue(again.history_done)
        self.assertTrue(again.has("Aleoida Arcus"))


if __name__ == "__main__":
    unittest.main()


class Learning(unittest.TestCase):
    def saa(self, genus, name="Test A 1"):
        return {"event": "SAASignalsFound", "BodyName": name, "BodyID": 5, "SystemAddress": 1,
                "Signals": [{"Type_Localised": "Biological", "Count": 1}], "Genuses": [{"Genus_Localised": genus}]}

    def setup_state(self, learned, entries):
        from journal.bio_predict import BioLearned
        bus, got = EventBus(), []
        state = GameState()
        state.system = "Test"
        state.bio = BioPredictor(codex=BioCodex(), learned=learned)
        state.bio.set_system("Test")
        proc = EventProcessor(bus, {}, state, load_registry())
        for e in entries:
            proc.handle_entry(e)
        return state

    def test_missed_genus_is_learned_and_counted_once(self):
        from journal.bio_predict import BioLearned
        path = Path(tempfile.mkdtemp()) / "l.json"
        learned = BioLearned(path)
        base = [planet("Test A 1", k=177), fss("Test A 1", 1)]
        state = self.setup_state(learned, base + [self.saa("Brain Tree")] + [self.saa("Brain Tree")])
        self.assertEqual(learned.stats["braintree"]["hit"], 1)          # replayed line not counted twice
        self.assertGreaterEqual(learned.stats["tussock"]["seen"], 1)
        self.assertEqual(learned.stats["tussock"]["hit"], 0)
        # a second, similar planet now lists Brain Trees as a candidate and Tussock counts for less
        again = BioLearned(path)
        state2 = self.setup_state(again, [planet("Test B 1", k=177), fss("Test B 1", 1)])
        genera = state2.bio.bodies["Test B 1"].candidate_genera()
        self.assertTrue(any("Brain" in g for g in genera))
        self.assertLess(again.weight("Tussock"), again.weight("Brain Tree"))

    def test_envelope_must_match(self):
        from journal.bio_predict import BioLearned
        learned = BioLearned()
        self.setup_state(learned, [planet("Test A 1", k=177), fss("Test A 1", 1), self.saa("Brain Tree")])
        state = self.setup_state(learned, [planet("Test B 1", k=700), fss("Test B 1", 1)])
        self.assertFalse(any("Brain" in g for g in state.bio.bodies["Test B 1"].candidate_genera()))

    def test_licence_exists(self):
        self.assertTrue((Path(__file__).resolve().parent.parent / "LICENSE").exists())


class GreenGasGiants(unittest.TestCase):
    """Real journals: a green gas giant is a codex entry named $Codex_Ent_Green_Sudarsky_Class_I_Name; (or ..._II_...), not a planet class."""

    def codex(self, new=True):
        return {"event": "CodexEntry", "Name": "$Codex_Ent_Green_Sudarsky_Class_I_Name;", "Name_Localised": "Green gas giant",
                "SubCategory_Localised": "Gas giant planets", "IsNewEntry": new, "System": "Somewhere"}

    def test_codex_entry_makes_the_event_and_replaces_the_plain_line(self):
        got, _ = run([self.codex()])
        names = [n for n, _ in got]
        self.assertIn("GreenGasGiant", names)
        self.assertNotIn("CodexEntry", names)
        self.assertTrue(dict(got)["GreenGasGiant"]["New"])

    def test_ordinary_codex_entries_are_not_green(self):
        got, _ = run([{"event": "CodexEntry", "Name": "$Codex_Ent_Standard_Sudarsky_Class_I_Name;", "Name_Localised": "Standard gas giant"}])
        self.assertNotIn("GreenGasGiant", [n for n, _ in got])

    def test_gas_giant_with_life_is_not_called_green(self):
        from personality.line_keys import scan_keys
        self.assertEqual(scan_keys({"PlanetClass": "Gas giant with water based life"}), ["Scan_LifeGasGiant"])
        self.assertEqual(scan_keys({"PlanetClass": "Water giant"}), ["Scan_RareGiant"])
        self.assertEqual(scan_keys({"PlanetClass": "Sudarsky class II gas giant"}), [])

    def test_lines_exist(self):
        from tests.test_dialogue import real_dialogue
        d = real_dialogue()
        for key in ("GreenGasGiant", "GreenGasGiant_New", "Scan_LifeGasGiant", "Scan_RareGiant"):
            self.assertTrue(d.pick(key, "Friendly", False, False), key)


def organic(species, stage, genus="Radicoida", body=3):
    return {"event": "ScanOrganic", "ScanType": stage, "Genus_Localised": genus, "Species_Localised": species, "Variant_Localised": species, "Body": body}


class UniqueSpecies(unittest.TestCase):
    def test_radicoida_unica_gets_its_own_line_and_nothing_else(self):
        got, state = run([organic("Radicoida Unica", "Log")])
        names = [n for n, _ in got]
        self.assertIn("UniqueBio", names)
        self.assertEqual(dict(got)["UniqueBio"]["Species"], "Radicoida Unica")

    def test_unique_species_never_taught_to_learner(self):
        from journal.bio_predict import BioLearned
        learned = BioLearned()
        learned.observe("sys|1", {"pc": "rocky", "atm": "none", "volc": "", "thin": 0, "k": 150, "g": 0.1}, ["Aleoida"], ["Radicoida"])
        self.assertNotIn("radicoida", learned.stats)
        self.assertNotIn("radicoida", learned.envelopes)

    def test_it_counts_for_the_codex_without_a_progress_line(self):
        got, state = run([organic("Radicoida Unica", "Analyse")])
        self.assertTrue(state.bio.codex.has("Radicoida Unica"))
        self.assertNotIn("BioProgress", [n for n, _ in got])

    def test_price_is_known(self):
        values = json.loads((Path(__file__).resolve().parent.parent / "config" / "exobiology_values.json").read_text(encoding="utf-8"))["values"]
        self.assertGreater(values["Radicoida Unica"], 1000000)


class CodexProgress(unittest.TestCase):
    def test_new_species_gets_a_progress_line_once(self):
        got, state = run([organic("Aleoida Arcus", "Analyse", genus="Aleoida")])
        data = dict(got)["BioProgress"]
        self.assertEqual(data["Count"], 1)
        self.assertGreater(data["Left"], 5)
        self.assertNotIn("Missing", data)
        got, _ = run([organic("Aleoida Arcus", "Analyse", genus="Aleoida"), organic("Aleoida Arcus", "Analyse", genus="Aleoida")])
        self.assertEqual([n for n, _ in got].count("BioProgress"), 1)

    def test_few_genera_left_are_named(self):
        _, state = run([])
        names = {r["n"].lower() for r in state.bio.rules}
        keep = [r for r in state.bio.rules if r["g"] not in ("Aleoida", "Tussock")]
        state.bio.codex.known = {r["n"].lower() for r in keep}
        data = state.bio.progress("Whatever")
        self.assertEqual(data["Left"], 2)
        self.assertIn("Aleoida", data["Missing"])
        self.assertIn(" and ", data["Missing"])

    def test_keys(self):
        from personality.line_keys import _keys_for
        from core.event_bus import Event
        self.assertEqual(_keys_for(Event("BioProgress", {"Missing": "A", "Left": 1}))[0], "BioProgress_Last")
        self.assertEqual(_keys_for(Event("BioProgress", {"Count": 3}))[0], "BioProgress")


class Milestones(unittest.TestCase):
    def stats(self, hours, jumps=100, foot=10, species=5):
        return {"event": "Statistics", "Exploration": {"Time_Played": hours * 3600, "Total_Hyperspace_Jumps": jumps, "First_Footfalls": foot},
                "Exobiology": {"Organic_Species_Encountered": species}}

    def test_first_time_only_writes_numbers_down(self):
        from journal.milestones import GameMilestones
        m = GameMilestones()
        self.assertEqual(m.check(self.stats(3789, 18265, 535, 78)), [])
        self.assertEqual(m.last["Hours"], 3789)

    def test_crossing_a_round_number_speaks_once(self):
        from journal.milestones import GameMilestones
        m = GameMilestones()
        m.check(self.stats(3789, 18265, 535, 78))
        self.assertEqual(m.check(self.stats(3790, 18300, 540, 78)), [])
        got = m.check(self.stats(4010, 20001, 601, 81))
        self.assertEqual(sorted(got), [("Footfalls", 600), ("Hours", 4000), ("Jumps", 20000), ("Species", 80)])
        self.assertEqual(m.check(self.stats(4010, 20001, 601, 81)), [])

    def test_statistics_line_makes_event(self):
        from journal.milestones import GameMilestones
        entries = [self.stats(499), self.stats(501)]
        got, state = run(entries)
        # run() uses a fresh GameMilestones that starts empty: the first line is the baseline, the second crosses 500 hours
        found = [d for n, d in got if n == "GameMilestone"]
        self.assertEqual([(d["Kind"], d["Value"], d["Number"]) for d in found], [("Hours", 500, "500")])
        self.assertNotIn("Statistics", [n for n, _ in got])

    def test_saved_between_runs(self):
        import tempfile, pathlib
        from journal.milestones import GameMilestones
        p = pathlib.Path(tempfile.mkdtemp()) / "m.json"
        GameMilestones(p).check(self.stats(100))
        self.assertEqual(GameMilestones(p).check(self.stats(600)), [("Hours", 500)])


class FirstDiscovery(unittest.TestCase):
    def test_rare_and_undiscovered_gets_first_line(self):
        from personality.line_keys import scan_keys
        self.assertEqual(scan_keys({"PlanetClass": "Earthlike body", "WasDiscovered": False}), ["Scan_EarthLike_First", "Scan_EarthLike"])
        self.assertEqual(scan_keys({"PlanetClass": "Earthlike body", "WasDiscovered": True}), ["Scan_EarthLike"])
        self.assertEqual(scan_keys({"PlanetClass": "Water giant", "WasDiscovered": False})[0], "Scan_RareGiant_First")
        self.assertEqual(scan_keys({"PlanetClass": "Rocky body", "WasDiscovered": False}), [])

    def test_lines_exist(self):
        from tests.test_dialogue import real_dialogue
        d = real_dialogue()
        for key in ("Scan_EarthLike_First", "Scan_WaterWorld_First", "Scan_AmmoniaWorld_First", "Scan_RareGiant_First", "UniqueBio",
                    "BioProgress", "BioProgress_Missing", "BioProgress_Last", "GameMilestone_Hours", "GameMilestone_Jumps",
                    "GameMilestone_Footfalls", "GameMilestone_Species", "GameMilestone"):
            self.assertTrue(d.pick(key, "Friendly", False, False), key)
