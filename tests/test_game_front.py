import time
import unittest

from ui import bio_overlay, game_front, hack_overlay, red_alert_overlay, settlement_overlay


class Settings(dict):
    def get(self, key, default=None):
        return dict.get(self, key, default)


class Away(unittest.TestCase):
    def setUp(self):
        game_front.reset()
        self.title = "Elite - Dangerous (CLIENT)"
        game_front.title_provider = lambda: self.title

    def tearDown(self):
        game_front.title_provider = None
        game_front.reset()

    def test_hidden_when_another_window_is_in_front(self):
        s = Settings()
        self.assertFalse(game_front.away(s, now=100.0))
        self.title = "Starling"
        self.assertTrue(game_front.away(s, now=101.0))
        self.title = "Elite - Dangerous (CLIENT)"
        self.assertFalse(game_front.away(s, now=102.0))

    def test_checked_at_most_twice_a_second(self):
        s = Settings()
        self.assertFalse(game_front.away(s, now=100.0))
        self.title = "Browser"
        self.assertFalse(game_front.away(s, now=100.2))

    def test_switch_off_and_unreadable_window(self):
        self.title = "Browser"
        self.assertFalse(game_front.away(Settings({"overlay.follow_game": False}), now=1.0))
        game_front.reset()
        self.title = None
        self.assertFalse(game_front.away(Settings(), now=2.0))


class Overlays(unittest.TestCase):
    def setUp(self):
        game_front.reset()
        game_front.title_provider = lambda: "Starling"

    def tearDown(self):
        game_front.title_provider = None
        game_front.reset()

    def test_biology_box_hides_and_test_button_still_shows(self):
        hidden = []
        box = bio_overlay.BioOverlay.__new__(bio_overlay.BioOverlay)
        box.settings, box.state_provider, box.test_until, box._signature = Settings(), (lambda: None), 0.0, ("old",)
        box._hide = lambda: hidden.append(1)
        box._update()
        self.assertEqual(hidden, [1])
        self.assertIsNone(box._signature)

        box.test_until, box._signature = time.monotonic() + 30, None
        box._screen_rect = lambda: (0, 0, 1920, 1080)
        box._draw = lambda *a: hidden.append("drawn")
        box._draw_focus = lambda *a: hidden.append("drawn")
        box._update()
        self.assertIn("drawn", hidden)

    def test_other_overlays_use_the_same_rule(self):
        for module in (red_alert_overlay, settlement_overlay, hack_overlay):
            self.assertTrue(hasattr(module, "game_front"), module.__name__)
        hack = hack_overlay.HackOverlay.__new__(hack_overlay.HackOverlay)
        hack.settings = Settings()
        hack._snap = lambda: {"anything": 1}
        self.assertFalse(hack._wanted())                 # Starling is in front, so no hack panel
        game_front.title_provider = lambda: "Elite - Dangerous (CLIENT)"
        game_front.reset()
        self.assertTrue(hack._wanted())


if __name__ == "__main__":
    unittest.main()
