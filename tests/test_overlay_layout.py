"""The Overlays page: boxes sit where the overlays really are, and dropping one saves what the real overlay reads."""

import unittest

from ui import bio_overlay, overlay_layout as L, route_overlay
from ui.settings_model import build_pages


class Settings(dict):
    def get(self, key, default=None):
        return dict.get(self, key, default)


SCREEN = (1920, 1080)


class RoundTripTests(unittest.TestCase):
    def test_every_box_saves_what_it_started_with(self):
        for box in L.BOXES:
            x, y, w, h = L.rect(box, Settings(), *SCREEN)
            values = L.settings_for(box, x, y, w, h)
            for key, value in values.items():
                self.assertAlmostEqual(value, float(L.DEFAULTS[key]), delta=0.11, msg=key)

    def test_bio_matches_the_overlays_own_placement(self):
        s = Settings({"overlay.bio_x": 10, "overlay.bio_up": 40})
        x, y, w, h = L.rect(L.box_for("bio"), s, *SCREEN)
        w_px, h_px = L.size_pixels(L.box_for("bio"), s, *SCREEN)
        expected = bio_overlay.placement(SCREEN[0], SCREEN[1], w_px, h_px, 10, 40)
        self.assertAlmostEqual(x * SCREEN[0], expected[0], delta=1)
        self.assertAlmostEqual(y * SCREEN[1], expected[1], delta=1)

    def test_route_matches_the_overlays_own_placement(self):
        s = Settings({"overlay.route_right": 5, "overlay.route_top": 20})
        box = L.box_for("route")
        x, y, w, h = L.rect(box, s, *SCREEN)
        w_px, h_px = L.size_pixels(box, s, *SCREEN)
        expected = route_overlay.placement(SCREEN[0], SCREEN[1], w_px, h_px, 5, 20)
        self.assertAlmostEqual(x * SCREEN[0], expected[0], delta=1)
        self.assertAlmostEqual(y * SCREEN[1], expected[1], delta=1)


class DropTests(unittest.TestCase):
    def test_dropped_top_left_gives_zero_gaps(self):
        v = L.settings_for(L.box_for("bio"), 0.0, 0.0, 0.1, 0.1)
        self.assertEqual(v, {"overlay.bio_x": 0.0, "overlay.bio_up": 90.0})

    def test_route_counts_from_the_right_and_top(self):
        v = L.settings_for(L.box_for("route"), 0.8, 0.25, 0.15, 0.3)
        self.assertEqual(v, {"overlay.route_right": 5.0, "overlay.route_top": 25.0})

    def test_dropping_off_the_edge_is_pulled_back_in(self):
        v = L.settings_for(L.box_for("hologram"), 2.0, 2.0, 0.08, 0.2)
        self.assertEqual(v["hologram.left"], 92.0)
        self.assertEqual(v["hologram.bottom"], 0.0)

    def test_gaps_never_go_over_the_overlays_own_limit(self):
        for box in L.BOXES:
            for x, y in ((0, 0), (1, 1), (0.5, 0.5)):
                for value in L.settings_for(box, x, y, 0.01, 0.01).values():
                    self.assertTrue(0.0 <= value <= 95.0)

    def test_nonsense_settings_fall_back_to_the_defaults(self):
        x, y, w, h = L.rect(L.box_for("bio"), Settings({"overlay.bio_x": "banana"}), *SCREEN)
        self.assertGreaterEqual(x, 0)


class PictureAndPageTests(unittest.TestCase):
    def test_drawing_has_the_asked_size(self):
        self.assertEqual(L.cockpit_picture(640, 360).size, (640, 360))

    def test_overlay_settings_live_on_the_overlays_page(self):
        pages = {p.id: p for p in build_pages()}
        keys = [f.key for f in pages["overlays"].fields]
        for key in ("hologram.enabled", "hologram.size", "overlay.screen", "overlay.bio_enabled", "overlay.route_map", "overlay.route_size"):
            self.assertIn(key, keys)
        everywhere = [f.key for p in pages.values() for f in p.fields]
        for gone in ("overlay.bio_x", "overlay.bio_up", "overlay.route_right", "overlay.route_top"):
            self.assertNotIn(gone, everywhere)
        self.assertEqual(len(everywhere), len(set(everywhere)), "a setting appears on two pages")

    def test_every_box_switch_is_a_real_setting(self):
        everywhere = {f.key for p in build_pages() for f in p.fields}
        for box in L.BOXES:
            if box.switch:
                self.assertIn(box.switch, everywhere)


if __name__ == "__main__":
    unittest.main()
