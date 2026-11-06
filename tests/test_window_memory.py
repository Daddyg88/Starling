"""The dashboard window comes back where she was last time (and never somewhere unreachable)."""
import unittest

from ui.window_memory import make_geometry, parse_geometry, usable_geometry

ONE = (0, 0, 1920, 1080)
TWO_LEFT = (-1920, 0, 3840, 1080)          # a second monitor to the left of the main one


class WindowMemoryTests(unittest.TestCase):
    def test_reading_and_writing_geometry(self):
        self.assertEqual(parse_geometry("1360x860+120+60"), (1360, 860, 120, 60))
        self.assertEqual(parse_geometry("1360x860+-1800+40"), (1360, 860, -1800, 40))
        self.assertEqual(parse_geometry("1360x860-5+10"), (1360, 860, -5, 10))
        self.assertIsNone(parse_geometry("nonsense"))
        self.assertIsNone(parse_geometry(""))
        self.assertEqual(make_geometry(1360, 860, -1800, 40), "1360x860-1800+40")
        self.assertEqual(parse_geometry(make_geometry(1360, 860, -1800, 40)), (1360, 860, -1800, 40))

    def test_a_good_position_is_kept(self):
        self.assertEqual(usable_geometry("1360x860+120+60", ONE), "1360x860+120+60")

    def test_second_monitor_on_the_left_is_remembered(self):
        self.assertEqual(usable_geometry("1360x860-1800+40", TWO_LEFT), "1360x860-1800+40")

    def test_unplugged_monitor_falls_back_to_the_default(self):
        self.assertIsNone(usable_geometry("1360x860-1800+40", ONE))            # that screen is gone
        self.assertIsNone(usable_geometry("1360x860+3000+40", ONE))
        self.assertIsNone(usable_geometry("1360x860+100+2000", ONE))

    def test_tiny_or_broken_sizes_are_ignored(self):
        self.assertIsNone(usable_geometry("200x100+10+10", ONE))
        self.assertIsNone(usable_geometry("garbage", ONE))

    def test_too_big_for_the_screen_is_shrunk(self):
        self.assertEqual(usable_geometry("3000x2000+0+0", ONE), "1920x1080+0+0")


if __name__ == "__main__":
    unittest.main()
