import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from navigation import radar_read as rr

FIXTURES = Path(__file__).parent / "fixtures" / "radar"      # real radar corners from a real play session (1920 x 1080)


def load(n):
    return np.asarray(Image.open(FIXTURES / ("radar_%02d.png" % n)).convert("RGB"))


def near(found, kind, x, y, tol=3):
    return any(i["kind"] == kind and abs(i["x"] - x) <= tol and abs(i["y"] - y) <= tol for i in found)


class FindIconsTests(unittest.TestCase):
    def test_a_terminal_at_the_edge(self):
        found = rr.find_icons(load(2))
        self.assertTrue(near(found, "terminal", 159, 73), found)
        self.assertEqual([i["kind"] for i in found].count("terminal"), 1)

    def test_ammo_and_a_gun_post_and_a_person_is_ignored(self):
        found = rr.find_icons(load(4))
        self.assertTrue(near(found, "ammo", 242, 99), found)
        self.assertTrue(near(found, "turret", 110, 127), found)
        self.assertFalse(any(i["kind"] == "turret" and abs(i["x"] - 190) < 6 and abs(i["y"] - 140) < 8 for i in found))     # the green ARROW is a person

    def test_two_terminals_and_two_recharge_points(self):
        found = rr.find_icons(load(5))
        self.assertTrue(near(found, "terminal", 158, 70), found)
        self.assertTrue(near(found, "terminal", 171, 159), found)
        self.assertTrue(near(found, "recharge", 136, 68), found)
        self.assertTrue(near(found, "recharge", 184, 70), found)

    def test_busy_picture(self):
        found = rr.find_icons(load(9))
        self.assertTrue(near(found, "terminal", 243, 133), found)
        self.assertTrue(near(found, "terminal", 259, 233), found)
        self.assertTrue(near(found, "turret", 244, 218), found)

    def test_your_own_arrow_is_not_an_icon(self):
        blank = np.zeros((308, 355, 3), dtype=np.uint8)
        self.assertEqual(rr.find_icons(blank), [])

    def test_the_crop_can_be_any_size(self):
        big = np.asarray(Image.fromarray(load(2)).resize((710, 616), Image.BILINEAR))
        found = rr.find_icons(big)
        self.assertTrue(near(found, "terminal", 159, 73, tol=4), found)


class GeometryTests(unittest.TestCase):
    def test_crop_box_scales_with_the_screen_height(self):
        self.assertEqual(rr.crop_box(1920, 1080), (67, 38, 422, 346))
        self.assertEqual(rr.crop_box(2560, 1440), (89, 51, 563, 461))
        left, top, right, bottom = rr.crop_box(1280, 720)
        self.assertLessEqual(right, 1280)

    def test_an_icon_ahead_is_north_when_facing_north(self):
        icon = {"kind": "terminal", "x": rr.ORIGIN[0], "y": rr.ORIGIN[1] - 2.2 * 20}        # 20 m ahead
        lat, lon = rr.to_position(icon, 10.0, 20.0, 0, 1_000_000.0)
        self.assertGreater(lat, 10.0)
        self.assertAlmostEqual(lon, 20.0, places=6)
        self.assertAlmostEqual(rr.metres_between((lat, lon), (10.0, 20.0), 1_000_000.0), 20.0, delta=0.05)

    def test_an_icon_ahead_is_east_when_facing_east(self):
        icon = {"kind": "terminal", "x": rr.ORIGIN[0], "y": rr.ORIGIN[1] - 2.2 * 30}
        lat, lon = rr.to_position(icon, 10.0, 20.0, 90, 1_000_000.0)
        self.assertGreater(lon, 20.0)
        self.assertAlmostEqual(lat, 10.0, places=6)

    def test_an_icon_on_the_right_is_east_when_facing_north(self):
        icon = {"kind": "terminal", "x": rr.ORIGIN[0] + 2.4 * 10, "y": rr.ORIGIN[1]}
        lat, lon = rr.to_position(icon, 0.0, 0.0, 0, 1_000_000.0)
        self.assertGreater(lon, 0.0)

    def test_missing_numbers_give_none(self):
        self.assertIsNone(rr.to_position({"x": 1, "y": 1}, None, 1, 1, 1000.0))
        self.assertIsNone(rr.to_position({"x": 1, "y": 1}, 1, 1, 1, 0))


if __name__ == "__main__":
    unittest.main()
