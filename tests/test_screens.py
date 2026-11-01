import unittest
from ui import screens
from ui.screens import Screen

MAIN = Screen(0, 0, 1920, 1080)
RIGHT = Screen(1920, 0, 3840, 1080)
LEFT = Screen(-1920, 0, 0, 1080)


class PickScreenTests(unittest.TestCase):
    def test_auto_follows_elite(self):
        self.assertEqual(screens.pick_screen("auto", [MAIN, RIGHT], (2500, 500)), RIGHT)
        self.assertEqual(screens.pick_screen("auto", [MAIN, RIGHT], (900, 500)), MAIN)

    def test_auto_without_game_uses_main(self):
        self.assertEqual(screens.pick_screen("auto", [RIGHT, MAIN], None), MAIN)

    def test_negative_coordinates(self):
        self.assertEqual(screens.pick_screen("auto", [MAIN, LEFT], (-500, 300)), LEFT)

    def test_numbered_left_to_right(self):
        both = [MAIN, LEFT]
        self.assertEqual(screens.pick_screen("1", both), LEFT)
        self.assertEqual(screens.pick_screen("2", both), MAIN)
        self.assertEqual(screens.pick_screen("4", both), MAIN)

    def test_primary(self):
        self.assertEqual(screens.pick_screen("primary", [RIGHT, MAIN], (2500, 5)), MAIN)

    def test_nothing_known(self):
        self.assertIsNone(screens.pick_screen("auto", [], None))
        self.assertEqual(screens.overlay_rect("auto", (1600, 900), screens=[], point=None), (0, 0, 1600, 900))

    def test_rect(self):
        self.assertEqual(screens.overlay_rect("2", (1, 1), screens=[MAIN, RIGHT]), (1920, 0, 1920, 1080))

    def test_not_windows_is_safe(self):
        self.assertEqual(screens.overlay_rect("auto", (800, 600)), (0, 0, 800, 600))


if __name__ == "__main__":
    unittest.main()
