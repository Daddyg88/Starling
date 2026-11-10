import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from navigation import settlement_share as share
from navigation import settlement_track
from navigation.settlement_maps import SettlementMaps, MapView
from tests.test_settlement_track import APPROACH, SHIP, Setup

MAPS = set(SettlementMaps().maps)


def entry(turn_a=(-0.1239, 0.3004), **more):
    base = {"v": 2, "map": "industrial_2", "a": list(turn_a), "t": [3.0, -374.0], "ref": [50.642288, -110.657997], "radius": 1074442.625,
            "name": "Shi Construction", "n": 5, "err": 6.0, "how": "stops"}
    base.update(more)
    return base


class Checking(unittest.TestCase):
    def test_a_sane_line_up_passes(self):
        self.assertIsNone(share.problem(entry(), MAPS))

    def test_bad_ones_are_named(self):
        for bad, word in ((entry(v=1), "older"), (entry(map="nowhere_9"), "unknown map"), (entry(turn_a=(0.9, 0.9)), "believable"),
                          (entry(radius=5), "radius"), (entry(ref=[200, 0]), "planet"), ({"v": 2}, "missing"), ("junk", "object"),
                          (entry(a=["x", 1]), "numbers"), ({"v": 2, "disabled": True}, "off")):
            self.assertIn(word, share.problem(bad, MAPS) or "", bad)

    def test_the_shipped_file_only_holds_good_entries(self):
        raw = json.loads((Path(settlement_track.paths.ROOT) / "maps" / "known_calibrations.json").read_text(encoding="utf-8"))
        for market, one in raw.items():
            if not market.startswith("_"):
                self.assertIsNone(share.problem(one, MAPS), market)

    def test_a_bad_shipped_entry_is_never_loaded(self):
        # the loader filters with the same check
        self.assertIn("4365483779", settlement_track.known_calibrations())


class Merging(unittest.TestCase):
    def test_new_ones_are_added_and_bad_ones_skipped(self):
        merged, report = share.merge({}, {"1": entry(), "2": entry(v=1)}, MAPS)
        self.assertEqual(list(merged), ["1"])
        self.assertTrue(any("added" in line for line in report))
        self.assertTrue(any("skipped 2" in line for line in report))

    def test_better_evidence_replaces_but_only_if_they_agree(self):
        have = {"1": entry(n=4, err=12.0)}
        merged, _ = share.merge(have, {"1": entry(n=7, err=3.0)}, MAPS)
        self.assertEqual(merged["1"]["n"], 7)
        merged, _ = share.merge(have, {"1": entry(n=4, err=20.0)}, MAPS)
        self.assertEqual(merged["1"]["err"], 12.0)

    def test_a_disagreement_is_reported_and_the_shipped_one_kept(self):
        have = {"1": entry()}
        merged, report = share.merge(have, {"1": entry(turn_a=(0.3, 0.1), n=9, err=1.0)}, MAPS)
        self.assertEqual(merged["1"]["n"], 5)
        self.assertTrue(any(line.startswith("CONFLICT") for line in report))
        merged, report = share.merge(have, {"1": entry(map="industrial_3", n=9)}, MAPS)
        self.assertTrue(any(line.startswith("CONFLICT") for line in report))

    def test_notes_are_not_settlements(self):
        merged, _ = share.merge({"_note": "x"}, {"_note": "y", "1": entry()}, MAPS)
        self.assertEqual(list(merged), ["1"])


class TheTool(unittest.TestCase):
    def load(self):
        root = Path(settlement_track.paths.ROOT) / "tools" / "merge_calibrations.py"
        spec = importlib.util.spec_from_file_location("merge_calibrations", root)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_it_reads_a_diagnostics_zip_and_a_plain_file(self):
        tool = self.load()
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "diag.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("settlement_calibration.json", json.dumps({"7": entry()}))
            self.assertEqual(list(tool.read_source(archive)), ["7"])
            plain = Path(folder) / "x.json"
            plain.write_text(json.dumps({"8": entry()}))
            self.assertEqual(list(tool.read_source(plain)), ["8"])
            empty = Path(folder) / "e.zip"
            with zipfile.ZipFile(empty, "w") as bundle:
                bundle.writestr("about.json", "{}")
            self.assertEqual(tool.read_source(empty), {})
            self.assertEqual(tool.read_source(Path(folder) / "missing.zip"), {})


class WhatIsSaved(Setup):
    def test_a_line_up_carries_what_is_needed_to_share_it(self):
        from navigation.settlement_track import Calibration
        cal = Calibration("industrial_2", complex(-0.1239, 0.3004), complex(3, -374), 50.6, -110.6, 1074442.625,
                          {"name": "Shi Construction", "n": 5, "err": 6.0, "how": "stops"})
        again = Calibration.from_json(cal.to_json())
        self.assertEqual(again.meta, {"name": "Shi Construction", "n": 5, "err": 6.0, "how": "stops"})
        self.assertIsNone(share.problem(cal.to_json(), MAPS))

    def test_resetting_a_settlement_also_turns_off_the_shipped_line_up(self):
        self.tracker.shipped = settlement_track.known_calibrations()
        self.tracker.on_entry(dict(APPROACH))
        self.assertIsNotNone(self.tracker.calibration)
        self.state.status_flags2 = 1
        self.tracker.try_handle("reset settlement map")
        self.assertIsNone(self.tracker.calibration)
        self.tracker.on_entry({"event": "SupercruiseEntry"})
        self.tracker.on_entry(dict(APPROACH))
        self.assertIsNone(self.tracker.calibration)
        self.assertTrue(self.tracker.saved["4365483779"]["disabled"])


if __name__ == "__main__":
    unittest.main()
