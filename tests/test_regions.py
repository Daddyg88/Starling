"""Galaxy regions: finding them, announcing a change, and the first time."""

import json
import tempfile
import unittest
from pathlib import Path

from core.event_bus import EventBus
from journal.game_state import GameState
from navigation.regions import RegionTracker, find_region, region_of, scan_journals
from tests.test_phase6b import make_settings

SOL, COLONIA, SAG = (0.0, 0.0, 0.0), (-9530.5, -910.28, 19808.1), (25.2, -20.9, 25899.97)


class Narr:
    def __init__(self):
        self.said = []

    def say(self, key, fields=None):
        self.said.append((key, (fields or {}).get("region")))
        return True


class Finding(unittest.TestCase):
    def test_known_places(self):
        self.assertEqual(find_region(*SOL)[1], "Inner Orion Spur")
        self.assertEqual(find_region(*SAG)[1], "Galactic Centre")
        self.assertIsNone(find_region(1e7, 0, 0))
        self.assertIsNone(region_of(None))
        self.assertIsNone(region_of((1, 2)))


class Tracker(unittest.TestCase):
    def build(self, start=SOL, visited=None, folder=None, **values):
        self.dir = Path(tempfile.mkdtemp())
        self.file = self.dir / "v.json"
        if visited is not None:
            self.file.write_text(json.dumps({"visited": visited}))
        self.state, self.narr, self.bus = GameState(), Narr(), EventBus()
        self.state.star_pos = start
        self.t = RegionTracker(self.bus, self.narr, make_settings(**values), lambda: self.state, journal_folder=folder,
                               visited_file=self.file, spawn=lambda fn: fn())
        self.t.attach()
        return self.t

    def jump(self, pos):
        self.state.star_pos = pos
        return self.t.on_jump()

    def test_same_region_is_silent(self):
        self.build(visited=[18])
        self.assertIsNone(self.jump((10.0, 0.0, 10.0)))
        self.assertEqual(self.narr.said, [])

    def test_new_region_first_time_then_known(self):
        self.build(visited=[18])
        self.assertEqual(self.jump(SAG), "first")
        self.assertEqual(self.narr.said[-1], ("RegionFirst", "Galactic Centre"))
        self.jump(SOL)
        self.assertEqual(self.jump(SAG), "entered")
        self.assertEqual(self.narr.said[-1], ("RegionEntered", "Galactic Centre"))
        self.assertIn(1, json.loads(self.file.read_text())["visited"])

    def test_known_region_just_entered(self):
        self.build(visited=[18, 9])
        self.assertEqual(self.jump(COLONIA), "entered")

    def test_nothing_on_load_but_it_is_remembered(self):
        self.build(start=None, visited=[])
        self.state.star_pos = SAG
        self.t.on_location()
        self.assertEqual(self.narr.said, [])
        self.assertEqual(self.jump(SAG), None)
        self.assertEqual(self.jump(SOL), "first")

    def test_switch_off(self):
        self.build(visited=[18], regions__announce=False)
        self.jump(SAG)
        self.assertEqual(self.narr.said, [])

    def test_first_run_scans_old_journals(self):
        folder = Path(tempfile.mkdtemp())
        lines = [{"event": "FSDJump", "StarSystem": "Colonia", "StarPos": list(COLONIA)},
                 {"event": "Scan", "BodyName": "x"}, {"event": "Location", "StarPos": list(SOL)}]
        (folder / "Journal.2026-01-01T000000.01.log").write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
        self.assertEqual(scan_journals(folder), {9, 18})
        self.build(folder=folder)
        self.assertEqual(self.t.visited, {9, 18})
        self.assertEqual(self.jump(COLONIA), "entered")          # already been there
        self.assertEqual(self.jump(SAG), "first")
        self.assertEqual(json.loads(self.file.read_text())["visited"], [1, 9, 18])

    def test_first_run_without_journals(self):
        self.build()
        self.assertEqual(self.t.visited, {18})

    def test_broken_file_is_ignored(self):
        self.build()
        self.file.write_text("nonsense")
        self.assertIsNone(self.t._load())


class Lines(unittest.TestCase):
    def test_lines(self):
        data = json.loads(Path("voicepacks/default/regions.json").read_text(encoding="utf-8"))
        banned = ("laugh", "giggle", "chortle", "uploading", "baka", "ug,", "uhh", "gtfo")
        for key in ("RegionEntered", "RegionFirst"):
            self.assertGreaterEqual(len(data[key]), 4)
        for key, lines in data.items():
            if key.startswith("_"):
                continue
            self.assertEqual(len(lines), len(set(lines)), key)
            for line in lines:
                self.assertIn("{region}", line)
                self.assertFalse([b for b in banned if b in line.lower()], line)
