"""tools/make_mouths.py: cut the mouth from a ComfyUI picture and fit it to her still picture."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import make_mouths as mm  # noqa: E402


class MouthToolTests(unittest.TestCase):
    def setUp(self):
        self.base = Image.open(mm.ASSETS / "base.jpg").convert("RGB")
        self.still = mm.to_small(self.base)

    def test_the_still_picture_matches_itself_with_no_shift(self):
        error, dx, dy = mm.find_shift(self.still, self.still)
        self.assertEqual((dx, dy), (0, 0))
        self.assertLess(error, 0.01)

    def test_a_moved_face_is_found(self):
        moved = Image.new("RGB", self.still.size)
        moved.paste(self.still, (0, 3))                 # face 3 pixels lower
        error, dx, dy = mm.find_shift(self.still, moved)
        self.assertEqual((dx, dy), (0, 3))               # look 3 pixels lower in the new picture

    def test_the_cut_out_has_the_right_size_and_keeps_the_old_shape(self):
        old = Image.open(mm.ASSETS / "ah.png").convert("RGBA")
        sprite = mm.make("ah", self.still, self.base, old)
        self.assertEqual(sprite.size, (mm.BOX[2], mm.BOX[3]))
        self.assertEqual(sprite.mode, "RGBA")
        self.assertTrue(np.array_equal(np.asarray(sprite)[..., 3], np.asarray(old)[..., 3]))

    def test_the_mouth_pictures_that_ship_are_the_right_size(self):
        meta = json.loads((mm.ASSETS / "hologram.json").read_text(encoding="utf-8"))
        for name in mm.NAMES:
            self.assertEqual(Image.open(mm.ASSETS / ("%s.png" % name)).size, (mm.BOX[2], mm.BOX[3]), name)
            self.assertIn(name, meta["sprites"])

    def test_the_blink_picture_is_fitted_the_same_way(self):
        old = Image.open(mm.ASSETS / "eyes.png").convert("RGBA")
        sprite = mm.make("eyes", self.still, self.base, old, box=mm.EYES_BOX, shift_box=(160, 215, 360, 300))
        self.assertEqual(sprite.size, (mm.EYES_BOX[2], mm.EYES_BOX[3]))
        self.assertEqual(Image.open(mm.ASSETS / "eyes.png").size, (250, 100))

    def test_the_tool_writes_the_blink_from_eyes_closed(self):
        folder = Path(tempfile.mkdtemp())
        self.still.save(folder / "eyes_closed.png")
        self.assertEqual(mm.main([str(folder), "--check"]), 0)
        self.assertTrue((folder / "check.png").exists())

    def test_a_wrong_size_picture_is_skipped(self):
        folder = Path(tempfile.mkdtemp())
        Image.new("RGB", (100, 100)).save(folder / "ah.png")
        self.assertEqual(mm.main([str(folder)]), 1)


if __name__ == "__main__":
    unittest.main()
