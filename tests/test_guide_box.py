import unittest

from ui import status


class GuideBox(unittest.TestCase):
    def test_sits_just_left_of_the_microphone_box(self):
        left, far = status.guide_box(1122)
        self.assertEqual(far, 1122 - 470 - 20)            # the mic box starts at right - 470
        self.assertEqual(far - left, status.GUIDE_WIDTH)

    def test_left_out_when_the_window_is_too_narrow(self):
        self.assertIsNone(status.guide_box(760))
        self.assertIsNotNone(status.guide_box(1122))

    def test_points_at_the_website(self):
        self.assertTrue(status.GUIDE_URL.startswith("https://daddyg88.github.io/Starling"))


if __name__ == "__main__":
    unittest.main()
