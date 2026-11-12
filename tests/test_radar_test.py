import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from navigation.radar_test import MAX_SAMPLES, RadarTest, crop_box

STATE = SimpleNamespace(latitude=55.4034, longitude=53.8026, heading=-15, planet_radius=1699980.5, status_flags2=33041, gui_focus=0)


class RadarTestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "radar_tests"
        self.file = Path(self.tmp.name) / "radar_samples.json"
        self.count = 0

    def make(self, state=STATE, picture="ok"):
        def stamp():
            self.count += 1
            return "t%03d" % self.count
        capture = (lambda: np.full((1080, 1920, 3), 90, dtype=np.uint8)) if picture == "ok" else (lambda: None)
        return RadarTest(lambda: state, capture=capture, out_folder=self.folder, samples_file=self.file,
                         settlement_name=lambda: "Shi Construction", stamp=stamp)

    def test_other_sentences_are_ignored(self):
        r = self.make()
        for said in ("what is the radar", "hello", "show settlement map", ""):
            self.assertIsNone(r.try_handle(said))
        self.assertFalse(self.folder.exists())

    def test_saves_only_the_radar_crop_and_the_position(self):
        r = self.make()
        for said in ("Radar test", "radar test.", "test the radar", "scan radar"):
            self.assertIn("saved", r.try_handle(said))
        rows = json.loads(self.file.read_text())
        self.assertEqual(len(rows), 4)
        row = rows[0]
        self.assertEqual((row["lat"], row["lon"], row["heading"]), (55.4034, 53.8026, -15))
        self.assertEqual(row["settlement"], "Shi Construction")
        self.assertEqual(row["window"], [1920, 1080])
        box = crop_box(1920, 1080)
        self.assertEqual(row["crop"], list(box))
        image = Image.open(self.folder / row["file"])
        self.assertEqual(image.size, (box[2] - box[0], box[3] - box[1]))
        self.assertLess(image.size[0], 400)              # a small corner of the screen, never the whole picture

    def test_the_crop_holds_the_radar_in_a_1080p_window(self):
        left, top, right, bottom = crop_box(1920, 1080)
        self.assertLessEqual(left, 85)                   # the N marker at x=85
        self.assertGreaterEqual(right, 380)              # the rim at x=378
        self.assertLessEqual(top, 90)
        self.assertGreaterEqual(bottom, 315)

    def test_no_position_no_picture(self):
        r = self.make(state=SimpleNamespace(latitude=None))
        self.assertIn("position", r.try_handle("radar test"))
        self.assertFalse(self.folder.exists())

    def test_game_window_not_seen(self):
        r = self.make(picture=None)
        self.assertIn("windowed or borderless", r.try_handle("radar test"))
        self.assertFalse(self.file.exists())

    def test_stops_at_the_limit(self):
        self.file.write_text(json.dumps([{"file": "x%d.png" % i} for i in range(MAX_SAMPLES)]))
        self.assertIn("clear", self.make().try_handle("radar test"))
        self.assertEqual(len(json.loads(self.file.read_text())), MAX_SAMPLES)


if __name__ == "__main__":
    unittest.main()
