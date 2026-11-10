import cmath
import math
import unittest

from navigation import settlement_solve
from navigation.settlement_maps import SettlementMaps, layout, projector, turned_size
from navigation.settlement_track import world_xy

RADIUS = 1074442.625
REF = (50.642288, -110.657997)
# three terminals walked to at Shi Construction (Industrial 2), 2026-11-09
TERMINALS = [(50.641743, -110.668892), (50.639, -110.653786), (50.640373, -110.651436)]


POWER_SPOT = [("power",) + world_xy(50.635338, -110.663132, REF[0], REF[1], RADIUS)]


def spots(points=TERMINALS):
    return [("terminal",) + world_xy(lat, lon, REF[0], REF[1], RADIUS) for lat, lon in points]


class Solving(unittest.TestCase):
    def setUp(self):
        self.maps = SettlementMaps()

    def test_real_terminals_find_the_right_turn(self):
        result = settlement_solve.solve(self.maps.get("industrial_2"), spots() + POWER_SPOT)
        self.assertTrue(settlement_solve.clear(result))
        self.assertAlmostEqual(math.degrees(cmath.phase(result["a"])), 111, delta=8)
        self.assertAlmostEqual(abs(result["a"]), 0.33, delta=0.03)

    def test_the_other_layouts_do_not_fit(self):
        for map_id in ("industrial_1", "industrial_3", "extraction_1", "military_2", "tourist_1", "agriculture_3"):
            self.assertFalse(settlement_solve.clear(settlement_solve.solve(self.maps.get(map_id), spots() + POWER_SPOT)), map_id)

    def test_too_few_spots_or_spots_too_close_give_nothing(self):
        data = self.maps.get("industrial_2")
        self.assertIsNone(settlement_solve.solve(data, spots(TERMINALS[:2])))
        self.assertIsNone(settlement_solve.solve(data, spots()))                  # three are not enough any more
        close = [("terminal", 0.0, 0.0), ("terminal", 3.0, 1.0), ("terminal", 5.0, 5.0)]
        self.assertIsNone(settlement_solve.solve(data, close))

    def test_a_spot_the_map_has_no_kind_for_is_ignored(self):
        data = self.maps.get("industrial_2")
        self.assertIsNone(settlement_solve.solve(data, spots(TERMINALS[:2]) + [("coffee",) + (0.0, 0.0)]))

    def test_two_spots_cannot_be_the_same_terminal(self):
        data = self.maps.get("industrial_2")
        spot = spots()[0]
        same = [spot, (spot[0], spot[1] + 25.0, spot[2]), (spot[0], spot[1] - 25.0, spot[2]), (spot[0], spot[1], spot[2] + 25.0)]
        self.assertFalse(settlement_solve.clear(settlement_solve.solve(data, [("terminal",) + s[1:] for s in same])))

    def test_one_stray_spot_among_four_does_not_spoil_it(self):
        stray = ("terminal", 400.0, 400.0)
        result = settlement_solve.solve(self.maps.get("industrial_2"), spots() + POWER_SPOT + [stray])
        self.assertAlmostEqual(math.degrees(cmath.phase(result["a"])), 111, delta=10)


class Turning(unittest.TestCase):
    def test_a_turned_map_is_bigger_than_the_picture(self):
        data = SettlementMaps().get("industrial_2")
        w, h = turned_size(data, 112)
        self.assertGreater(h, data["size"][1])
        self.assertEqual(turned_size(data, None), tuple(float(v) for v in data["size"]))

    def test_the_middle_stays_in_the_middle_and_north_goes_up(self):
        data = SettlementMaps().get("industrial_2")
        project, _ = projector(data, 500, 500, 90)
        cx, cy = data["size"][0] / 2.0, data["size"][1] / 2.0
        self.assertEqual(project(cx, cy), (250.0, 250.0))
        # turned 90 degrees anticlockwise: what was to the right of the middle is now above it
        x, y = project(cx + 100, cy)
        self.assertAlmostEqual(x, 250.0)
        self.assertLess(y, 250.0)

    def test_layout_without_a_turn_is_as_before(self):
        data = SettlementMaps().get("industrial_2")
        shape = layout(data, 400, 400)
        self.assertEqual(shape["project"](0, 0), (shape["offset"][0], shape["offset"][1]))


if __name__ == "__main__":
    unittest.main()
