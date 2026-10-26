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
