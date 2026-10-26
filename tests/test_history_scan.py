import json
import tempfile
import unittest
from pathlib import Path

from journal.bio_predict import BioCodex, BioLearned
from journal.exobiology import ExobiologyTracker
from journal.history_scan import HistoryScan

G = 9.80665


def lines(*entries):
    return "".join(json.dumps(e, separators=(",", ":")) + "\n" for e in entries)


class HistoryTests(unittest.TestCase):
    def make(self):
        self.journals = Path(tempfile.mkdtemp())
        self.data = Path(tempfile.mkdtemp())
        seed = self.data / "seed.json"
        seed.write_text(json.dumps({"values": {"Tussock Albata": 500000}}))
        self.tracker = ExobiologyTracker(seed, self.data)
        self.codex = BioCodex(self.data / "codex.json")
        self.learned = BioLearned(self.data / "learned.json")
        return HistoryScan(lambda: self.journals, self.codex, self.learned, self.tracker, self.data / "summary.json")

    def test_reads_everything_useful(self):
        scan = self.make()
        (self.journals / "Journal.2026-01-01T000000.01.log").write_text(
            lines({"event": "FSDJump", "StarSystem": "Alpha"},
                  {"event": "Scan", "BodyName": "Alpha A 1", "BodyID": 3, "PlanetClass": "Rocky body", "AtmosphereType": "CarbonDioxide",
                   "Atmosphere": "thin Carbon dioxide atmosphere", "SurfaceGravity": 0.2 * G, "SurfaceTemperature": 177, "Volcanism": ""},
                  {"event": "FSSBodySignals", "BodyName": "Alpha A 1", "BodyID": 3, "Signals": [{"Type_Localised": "Biological", "Count": 1}]},
                  {"event": "SAASignalsFound", "BodyName": "Alpha A 1", "BodyID": 3, "SystemAddress": 1,
                   "Signals": [{"Type_Localised": "Biological", "Count": 1}], "Genuses": [{"Genus_Localised": "Tussock"}]},
                  {"event": "CodexEntry", "Name_Localised": "Aleoida Arcus - Green"},
                  {"event": "CodexEntry", "Name_Localised": "Some Rock"},
                  {"event": "Music", "MusicTrack": "x"},
                  {"event": "SellOrganicData", "BioData": [{"Species_Localised": "Tussock Albata", "Value": 777000}]}))
        (self.journals / "Journal.2026-01-02T000000.01.log").write_text("not json\n" + lines({"event": "Died"}))
        self.assertIn("Reading", scan.start())
        scan._thread.join(10)
        self.assertFalse(scan.running)
        self.assertEqual(scan.summary["journals"], 2)
        self.assertEqual(self.codex.known, {"aleoida arcus"})
        self.assertTrue(self.codex.history_done)
        self.assertEqual(self.learned.stats["tussock"]["hit"], 1)
        self.assertEqual(self.tracker.base_value("Tussock Albata"), 777000)
        self.assertTrue((self.data / "summary.json").exists())
        self.assertIn("Read 2 journal files", scan.status())

    def test_second_run_adds_nothing_twice(self):
        scan = self.make()
        (self.journals / "Journal.2026-01-01T000000.01.log").write_text(
            lines({"event": "FSDJump", "StarSystem": "Alpha"},
                  {"event": "Scan", "BodyName": "Alpha A 1", "BodyID": 3, "PlanetClass": "Rocky body", "AtmosphereType": "CarbonDioxide",
                   "Atmosphere": "thin Carbon dioxide atmosphere", "SurfaceGravity": 0.2 * G, "SurfaceTemperature": 177, "Volcanism": ""},
                  {"event": "SAASignalsFound", "BodyName": "Alpha A 1", "BodyID": 3,
                   "Signals": [{"Type_Localised": "Biological", "Count": 1}], "Genuses": [{"Genus_Localised": "Tussock"}]}))
        for _ in range(2):
            scan.start()
            scan._thread.join(10)
        self.assertEqual(self.learned.stats["tussock"]["hit"], 1)

    def test_no_folder(self):
        scan = self.make()
        scan.folder_provider = lambda: None
        self.assertIn("can't find", scan.start())
        self.assertFalse(scan.running)


if __name__ == "__main__":
    unittest.main()


class LifeTests(unittest.TestCase):
    def test_other_memories_and_owned_systems(self):
        from database.db import Database
        from journal.owned_systems import OwnedSystems
        from memory.store import MemoryStore
        tmp = Path(tempfile.mkdtemp())
        db = Database(tmp / "t.db").initialise()
        self.addCleanup(db.close)
        store = MemoryStore(db)
        store.increment("systems_visited", 1000)               # live counter already bigger than the journals: stays
        owned = OwnedSystems(tmp / "owned.json")
        journals = Path(tempfile.mkdtemp())
        (journals / "Journal.2026-01-01T000000.01.log").write_text(
            lines({"timestamp": "2026-01-01T10:00:00Z", "event": "LoadGame"},
                  {"timestamp": "2026-01-01T10:01:00Z", "event": "FSDJump", "StarSystem": "Alpha", "JumpDist": 55.5},
                  {"timestamp": "2026-01-01T10:02:00Z", "event": "FSDJump", "StarSystem": "Beta", "JumpDist": 12.0},
                  {"timestamp": "2026-01-01T10:03:00Z", "event": "MissionCompleted", "Reward": 9000000, "LocalisedName": "Big job"},
                  {"timestamp": "2026-01-01T10:04:00Z", "event": "MissionCompleted", "Reward": 1000, "LocalisedName": "Small job"},
                  {"timestamp": "2026-01-01T10:05:00Z", "event": "Died", "KillerName": "Cmdr Bad"},
                  {"timestamp": "2026-01-01T10:06:00Z", "event": "SellExplorationData", "TotalEarnings": 2500000},
                  {"timestamp": "2026-01-01T10:07:00Z", "event": "ColonisationSystemClaim", "StarSystem": "Mine 1", "SystemAddress": 9},
                  {"timestamp": "2026-01-01T10:08:00Z", "event": "ColonisationSystemClaim", "StarSystem": "Mine 2", "SystemAddress": 10},
                  {"timestamp": "2026-01-01T10:09:00Z", "event": "ColonisationSystemClaimRelease", "StarSystem": "Mine 2"},
                  {"timestamp": "2026-01-01T12:00:00Z", "event": "Shutdown"}))
        data = Path(tempfile.mkdtemp())
        tracker = ExobiologyTracker(None, data)
        scan = HistoryScan(lambda: journals, BioCodex(), BioLearned(), tracker, None, store, owned)
        scan.start()
        scan._thread.join(10)
        stats = store.stats()
        self.assertEqual(stats["systems_visited"], 1000)
        self.assertEqual(stats["missions_completed"], 2)
        self.assertEqual(stats["times_destroyed"], 1)
        self.assertAlmostEqual(stats["hours_together"], 2.0, places=2)
        self.assertIn("55.5", store.record("longest_jump")["summary"])
        self.assertIn("Big job", store.by_kind("big_mission")[0]["summary"])
        self.assertEqual(len(store.by_kind("big_mission")), 1)
        self.assertEqual(owned.names(), ["Mine 1"])
        self.assertIn("You own 1 system", scan.status())
        scan.start()
        scan._thread.join(10)
        self.assertEqual(store.stats()["missions_completed"], 2)       # running it again changes nothing
        self.assertEqual(len(store.by_kind("death")), 1)


class OwnedArrival(unittest.TestCase):
    def test_welcome_home(self):
        from core.event_bus import EventBus
        from events.registry import load_registry
        from journal.game_state import GameState
        from journal.owned_systems import OwnedSystems
        from journal.processor import EventProcessor
        bus, got = EventBus(), []
        bus.subscribe("*", lambda e: got.append((e.name, e.data)))
        state = GameState()
        state.owned = OwnedSystems(Path(tempfile.mkdtemp()) / "o.json")
        proc = EventProcessor(bus, {}, state, load_registry())
        proc.handle_entry({"event": "ColonisationSystemClaim", "StarSystem": "Home Sys", "SystemAddress": 5, "timestamp": "t"})
        self.assertTrue(state.owned.has("home sys"))
        proc.handle_entry({"event": "FSDJump", "StarSystem": "Elsewhere", "JumpDist": 5, "FuelUsed": 1, "FuelLevel": 10, "StarClass": "K"})
        self.assertNotIn("OwnSystemArrival", [n for n, _ in got])
        proc.handle_entry({"event": "FSDJump", "StarSystem": "Home Sys", "JumpDist": 5, "FuelUsed": 1, "FuelLevel": 10, "StarClass": "K"})
        self.assertEqual(dict(got)["OwnSystemArrival"]["StarSystem"], "Home Sys")
        reloaded = OwnedSystems(state.owned.path)
        self.assertTrue(reloaded.has("Home Sys"))                 # survives a restart
        proc.handle_entry({"event": "ColonisationSystemClaimRelease", "StarSystem": "Home Sys"})
        self.assertFalse(state.owned.has("Home Sys"))


class StatisticsHours(unittest.TestCase):
    def test_statistics_play_time_wins_over_file_span(self):
        from database.db import Database
        from memory.store import MemoryStore
        tmp = Path(tempfile.mkdtemp())
        db = Database(tmp / "t.db").initialise()
        self.addCleanup(db.close)
        store = MemoryStore(db)
        journals = Path(tempfile.mkdtemp())
        (journals / "Journal.2026-01-01T000000.01.log").write_text(
            lines({"timestamp": "2026-01-01T10:00:00Z", "event": "LoadGame"},
                  {"timestamp": "2026-01-01T10:01:00Z", "event": "Statistics", "Exploration": {"Time_Played": 7200}},
                  {"timestamp": "2026-01-02T10:00:00Z", "event": "Shutdown"}))
        scan = HistoryScan(lambda: journals, BioCodex(), BioLearned(), ExobiologyTracker(None, Path(tempfile.mkdtemp())), None, store, None)
        scan.start()
        scan._thread.join(10)
        self.assertAlmostEqual(store.stats()["hours_together"], 2.0, places=2)
