import json
import math
import tempfile
import unittest
from pathlib import Path

from navigation import radar_match
from navigation.radar_points import MERGE_METRES, PointStore
from navigation.settlement_maps import SettlementMaps

RADIUS = 1_700_000.0
PER_DEGREE = math.pi / 180.0 * RADIUS


def at(lat0, lon0, north, east):
    return lat0 + north / PER_DEGREE, lon0 + east / (PER_DEGREE * math.cos(math.radians(lat0)))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "radar_points.json"
        self.store = PointStore(self.path, stamp=lambda: "2026-11-12T20:00:00Z")

    def test_repeat_sightings_become_one_point_with_an_average(self):
        a = at(55.4, 53.8, 10, 10)
        b = at(55.4, 53.8, 12, 9)               # 2 m away: the same terminal
        self.store.add_picture("M1", [("terminal", *a)], (55.4, 53.8), RADIUS)
        added = self.store.add_picture("M1", [("terminal", *b)], (55.4, 53.8), RADIUS)
        self.assertEqual(added, 0)
        points = self.store.points("M1", "terminal")
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["n"], 2)
        self.assertAlmostEqual(points[0]["lat"], (a[0] + b[0]) / 2, places=6)

    def test_far_apart_or_different_kinds_are_different_points(self):
        a = at(55.4, 53.8, 0, 0)
        far = at(55.4, 53.8, 0, MERGE_METRES + 3)
        self.store.add_picture("M1", [("terminal", *a), ("terminal", *far), ("ammo", *a)], (55.4, 53.8), RADIUS)
        self.assertEqual(self.store.counts("M1"), {"terminal": 2, "ammo": 1, "recharge": 0, "turret": 0})

    def test_coverage_counts_new_squares_only(self):
        self.store.add_picture("M1", [], (55.4, 53.8), RADIUS)
        self.store.add_picture("M1", [], at(55.4, 53.8, 2, 2), RADIUS)             # same 12 m square
        self.store.add_picture("M1", [], at(55.4, 53.8, 40, 0), RADIUS)            # a new one
        self.assertEqual(len(self.store.get("M1")["cells"]), 2)
        self.assertEqual(self.store.get("M1")["pictures"], 3)

    def test_it_saves_and_loads_again(self):
        self.store.describe("M1", name="Makubuya", group="Industrial", pads={"Small": 0, "Medium": 0, "Large": 1})
        self.store.add_picture("M1", [("terminal", *at(55.4, 53.8, 5, 5))], (55.4, 53.8), RADIUS)
        self.store.mark_done("M1")
        self.store.save()
        again = PointStore(self.path)
        self.assertEqual(again.get("M1")["name"], "Makubuya")
        self.assertTrue(again.get("M1")["done"])
        self.assertEqual(len(again.points("M1")), 1)

    def test_a_broken_file_is_ignored(self):
        self.path.write_text("not json")
        self.assertEqual(PointStore(self.path).data, {})

    def test_terminals_in_metres_from_the_first_place_you_stood(self):
        self.store.add_picture("M1", [("terminal", *at(55.4, 53.8, 30, 40))], (55.4, 53.8), RADIUS)
        (east, north), = self.store.terminals_metres("M1")
        self.assertAlmostEqual(east, 40, delta=0.1)
        self.assertAlmostEqual(north, 30, delta=0.1)

    def test_unknown_settlement_is_empty(self):
        self.assertEqual(self.store.points("nope"), [])
        self.assertEqual(self.store.terminals_metres("nope"), [])


class MatchTests(unittest.TestCase):
    """Real radar spots measured at Makubuya Engineering Silo (an Industrial 2)."""

    @classmethod
    def setUpClass(cls):
        spots = json.loads((Path(__file__).parent / "fixtures" / "makubuya_radar_spots.json").read_text())
        spots.sort(key=lambda s: -s["seen"])
        cls.points = [complex(s["e"], s["n"]) for s in spots]
        cls.maps = SettlementMaps()

    def test_industrial_2_fits_best_of_the_industrial_layouts(self):
        rows = radar_match.rank(self.points, self.maps, ["industrial_%d" % i for i in range(1, 6)])
        self.assertEqual(rows[0][0], "industrial_2")

    def test_with_the_pad_counts_narrowing_it_to_two_it_is_clear(self):
        found, rows = radar_match.suggest(self.points, self.maps, ["industrial_2", "industrial_5"])
        self.assertEqual(found, "industrial_2", rows)

    def test_it_stays_quiet_when_it_is_not_clear(self):
        found, _rows = radar_match.suggest(self.points, self.maps, ["industrial_%d" % i for i in range(1, 6)])
        self.assertIsNone(found)

    def test_too_few_terminals_never_decide(self):
        found, _rows = radar_match.suggest(self.points[:2], self.maps, ["industrial_2", "industrial_5"])
        self.assertIsNone(found)


if __name__ == "__main__":
    unittest.main()
