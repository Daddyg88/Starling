import json
import math
import tempfile
import unittest
from pathlib import Path

from navigation.settlement_maps import SettlementMaps
from tools import add_marked_terminals as tool

REF = {"Name": "Sharma Hydroponics Farm", "MarketID": 4358317571, "Latitude": 9.453527, "Longitude": -94.412834, "map_shown": "agriculture_4"}
R = 1104864.0


def mark(lat, lon, when):
    return {"label": "terminal", "time": when, "lat": lat, "lon": lon, "heading": 0.0, "radius": R, "on_foot": True, "map": "agriculture_4"}


# Ben's real marks at Sharma Hydroponics Farm, 15 Nov 2026: A between AGRI and STO, B outside the top AGRI, C by the Large pad
A, B, C = (9.454846, -94.411537), (9.460864, -94.411568), (9.440289, -94.41172)
SHIP = (9.445112, -94.408699)


def visit(marks, trail=True):
    return {"started": "2026-11-15T11:42:32Z", "settlement": dict(REF), "marks": marks, "trail": [[SHIP[0], SHIP[1], -121.0]] if trail else []}


class Tool(unittest.TestCase):
    def setUp(self):
        data = dict(SettlementMaps().get("agriculture_4"))
        data["markers"] = [m for m in data["markers"] if not m.get("marked")]          # the map as it was before the terminal by the pad was added
        self.data = data

    def places(self, marks):
        groups = tool.gather([visit(marks)])
        entry = next(iter(groups.values()))
        return groups, entry, tool.distinct(entry["marks"])

    def test_it_finds_the_turn_and_size_and_the_terminal_the_map_lacks(self):
        groups, entry, places = self.places([mark(*A, "t1"), mark(*B, "t2"), mark(*C, "t3"), mark(*C, "t4")])
        cal, matched, missing = tool.solve(self.data, places, entry["ships"])
        self.assertEqual((matched, missing), (2, 1))
        self.assertAlmostEqual(abs(cal.a), 0.37, delta=0.02)
        e, n, count = places[2]
        x, y = cal.from_world(e, n)
        self.assertLess(math.hypot(x - 533, y - 1139), 20.0)
        self.assertEqual(count, 2)

    def test_the_ship_tells_the_map_from_the_same_map_turned_half_way(self):
        groups, entry, places = self.places([mark(*A, "t1"), mark(*B, "t2"), mark(*C, "t3")])
        self.assertIsNone(tool.solve(self.data, places, None))               # without the ship two answers fit equally
        self.assertIsNotNone(tool.solve(self.data, places, entry["ships"]))

    def test_one_matching_terminal_is_not_enough(self):
        groups, entry, places = self.places([mark(*A, "t1"), mark(*C, "t2")])
        self.assertIsNone(tool.solve(self.data, places, entry["ships"]))

    def test_marks_on_an_unknown_map_or_off_foot_are_ignored(self):
        bad = mark(*A, "t1")
        bad["on_foot"] = False
        v = visit([bad])
        self.assertEqual(tool.gather([v]), {})

    def test_repeated_visits_are_counted_once_each(self):
        first, second = visit([mark(*A, "t1")]), visit([mark(*A, "t2")])
        second["started"] = "2026-11-15T12:00:00Z"
        self.assertEqual(len(tool.load_visits([])), 0)
        entry = next(iter(tool.gather([first, second]).values()))
        self.assertEqual(tool.distinct(entry["marks"])[0][2], 2)

    def test_adding_a_marker_keeps_the_file_valid_and_the_layout(self):
        source = Path(__file__).resolve().parent.parent / "maps" / "settlements" / "agriculture_4.json"
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / "agriculture_4.json"
            copy.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            before = len(json.loads(copy.read_text(encoding="utf-8"))["markers"])
            tool.add_markers(copy, [(600, 1100)], [0, 0, 1634, 1200])
            data = json.loads(copy.read_text(encoding="utf-8"))
            self.assertEqual(len(data["markers"]), before + 1)
            self.assertEqual(data["bounds"], [0, 0, 1634, 1200])
            self.assertEqual(data["markers"][-1]["type"], "terminal_l0")

    def test_the_shipped_agriculture_4_has_the_terminal_by_the_large_pad(self):
        data = SettlementMaps().get("agriculture_4")
        terminals = [m for m in data["markers"] if str(m["type"]).startswith("terminal")]
        self.assertTrue(any(math.hypot(m["x"] - 533, m["y"] - 1139) < 25 for m in terminals))
        self.assertGreaterEqual(data["bounds"][3], max(m["y"] for m in terminals))
