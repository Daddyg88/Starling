import json
import tempfile
import unittest
from pathlib import Path

from control.settlement_voice import SettlementMapVoice
from navigation import settlement_maps
from navigation.settlement_maps import MapView, SettlementMaps, layout

SMALL = {"id": "tourist_1", "name": "Tourist 1", "group": "Tourist", "size": [200, 100], "credit": "Map by CMDR Quizengine",
         "buildings": [{"rect": [10, 10, 50, 40]}], "circles": [{"x": 100, "y": 50, "r": 20}], "labels": [{"text": "HAB", "x": 5, "y": 5}],
         "markers": [{"type": "airlock", "x": 10, "y": 10, "level": 2}, {"type": "power", "x": 60, "y": 60}, {"type": "door", "x": 70, "y": 70, "level": 1}]}


class Loading(unittest.TestCase):
    def test_the_shipped_maps_load_and_are_well_formed(self):
        maps = SettlementMaps()
        self.assertIn("tourist_1", maps.maps)
        for data in maps.maps.values():
            width, height = data["size"]
            for marker in data["markers"]:
                self.assertIn(marker["type"], settlement_maps.COLOURS, data["id"])
                self.assertTrue(0 <= marker["x"] <= width and 0 <= marker["y"] <= height, (data["id"], marker))
            self.assertTrue(data["credit"])

    def test_the_credit_file_is_there(self):
        self.assertIn("Quizengine", (settlement_maps.maps_folder() / "CREDITS.md").read_text(encoding="utf-8"))

    def test_broken_files_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "bad.json").write_text("{nope")
            (Path(tmp) / "good.json").write_text(json.dumps(SMALL))
            (Path(tmp) / "other.json").write_text(json.dumps({"id": "x"}))
            self.assertEqual(list(SettlementMaps(tmp).maps), ["tourist_1"])
        self.assertEqual(SettlementMaps("/nowhere/at/all").maps, {})

    def test_finding_a_map_by_what_you_say(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.json").write_text(json.dumps(SMALL))
            maps = SettlementMaps(tmp)
            for said in ("tourist one", "show settlement map tourist 1", "Tourist-1"):
                self.assertEqual(maps.find(said)["id"], "tourist_1", said)
            self.assertEqual(maps.find("tourist")["id"], "tourist_1")      # only one in the group
            self.assertIsNone(maps.find("tourist two"))
            self.assertIsNone(maps.find("military one"))


class Drawing(unittest.TestCase):
    def test_scaled_to_the_box_keeping_the_shape(self):
        shape = layout(SMALL, 400, 400)
        xs = [p for line in shape["lines"] for p in (line[0], line[2])]
        self.assertAlmostEqual(min(xs), 20.0)                  # scale 2: x 10 -> 20
        ys = [p for line in shape["lines"] for p in (line[1], line[3])]
        self.assertAlmostEqual(min(ys), 100 + 20.0)            # centred up and down: 100 px of spare height / 2 = 100
        self.assertEqual(len(shape["lines"]), 4)
        self.assertEqual(shape["circles"][0][2], 40.0)
        self.assertEqual([m[3] for m in shape["markers"]], ["2", "P", "1"])
        self.assertIn("Quizengine", shape["credit"])


class Voice(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        (Path(self.tmp.name) / "a.json").write_text(json.dumps(SMALL))
        self.view = MapView()
        self.voice = SettlementMapVoice(SettlementMaps(self.tmp.name), self.view)

    def test_show_and_hide(self):
        self.assertIn("Tourist 1", self.voice.try_handle("show the settlement map tourist one"))
        self.assertEqual(self.view.current, "tourist_1")
        self.assertIn("hidden", self.voice.try_handle("hide the settlement map"))
        self.assertIsNone(self.view.current)

    def test_without_a_name_she_asks_which_one(self):
        self.assertIn("Which settlement map", self.voice.try_handle("show settlement map"))
        self.assertIsNone(self.view.current)

    def test_other_sentences_are_left_alone(self):
        for said in ("show the biology overlay", "what is the next jump", "settlement", ""):
            self.assertIsNone(self.voice.try_handle(said), said)


class AllTheLayouts(unittest.TestCase):
    def test_all_28_odyssey_layouts_are_shipped_with_the_credit(self):
        maps = SettlementMaps()
        self.assertEqual(len(maps.maps), 28)
        counts = {}
        for data in maps.maps.values():
            counts[data["group"]] = counts.get(data["group"], 0) + 1
            self.assertIn("Quizengine", data["credit"])
            self.assertTrue(data["markers"])
        self.assertEqual(counts, {"Tourist": 4, "Agriculture": 5, "Military": 5, "Industrial": 5, "Extraction": 5, "High Tech": 4})
