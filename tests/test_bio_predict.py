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

    def test_no_scan_means_unknown_guess(self):
        got, state = run([fss("Test A 1", 1)])
        self.assertTrue(dict(got)["BioGuess"].get("Unknown"))

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
