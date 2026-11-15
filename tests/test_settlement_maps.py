import json
import math
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
                bx0, by0, bx1, by1 = settlement_maps.bounds(data)            # (a map may reach past its picture: 0.96.26)
                self.assertTrue(bx0 <= marker["x"] <= bx1 and by0 <= marker["y"] <= by1, (data["id"], marker))
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
    # Pad counts as (Small, Medium, Large). Read by Benny from the Odyssey Map Guide pictures (best guesses, not game data),
    # except Industrial 2 (Shi) and Tourist 1 which came from real journal LandingPads. If one is wrong, fix the map file AND this table.
    PADS = {"tourist_1": (2, 0, 2), "tourist_2": (0, 1, 0), "tourist_3": (2, 0, 1), "tourist_4": (1, 0, 1),
            "agriculture_1": (1, 0, 1), "agriculture_2": (1, 0, 0), "agriculture_3": (1, 0, 1), "agriculture_4": (2, 0, 1), "agriculture_5": (1, 0, 0),
            "military_1": (0, 1, 0), "military_2": (2, 0, 1), "military_3": (1, 1, 0), "military_4": (1, 0, 0), "military_5": (1, 1, 0),
            "industrial_1": (1, 0, 0), "industrial_2": (0, 0, 1), "industrial_3": (0, 1, 0), "industrial_4": (1, 0, 1), "industrial_5": (0, 0, 1),
            "extraction_1": (1, 0, 1), "extraction_2": (1, 0, 1), "extraction_3": (0, 0, 1), "extraction_4": (0, 1, 0), "extraction_5": (1, 0, 0),
            "high_tech_1": (1, 0, 1), "high_tech_2": (1, 0, 0), "high_tech_3": (1, 0, 0), "high_tech_4": (3, 0, 0)}

    def test_every_layout_has_the_pad_counts_from_the_guide(self):
        maps = SettlementMaps()
        self.assertEqual(set(maps.maps), set(self.PADS))
        for map_id, data in maps.maps.items():
            got = (data["pads"]["Small"], data["pads"]["Medium"], data["pads"]["Large"])
            self.assertEqual(got, self.PADS[map_id], map_id)

    def test_all_28_odyssey_layouts_are_shipped_with_the_credit(self):
        maps = SettlementMaps()
        self.assertEqual(len(maps.maps), 28)
        counts = {}
        for data in maps.maps.values():
            counts[data["group"]] = counts.get(data["group"], 0) + 1
            self.assertIn("Quizengine", data["credit"])
            self.assertTrue(data["markers"])
        self.assertEqual(counts, {"Tourist": 4, "Agriculture": 5, "Military": 5, "Industrial": 5, "Extraction": 5, "High Tech": 4})


class GroundOutlines(unittest.TestCase):
    """0.96.9: dim wall and pad outlines under the wireframe (only some maps have them)."""

    def test_no_ground_means_no_ground_lines(self):
        self.assertEqual(layout(SMALL, 400, 400)["ground"], [])

    def test_ground_outlines_are_drawn_as_closed_lines(self):
        data = dict(SMALL, ground=[[[0, 0], [10, 0], [10, 10]]])
        lines = layout(data, 400, 400)["ground"]
        self.assertEqual(len(lines), 3)                                  # a triangle: three sides, closed
        self.assertEqual((lines[2][2], lines[2][3]), (lines[0][0], lines[0][1]))

    def test_a_broken_outline_with_two_points_is_ignored(self):
        data = dict(SMALL, ground=[[[0, 0], [10, 0]]])
        self.assertEqual(layout(data, 400, 400)["ground"], [])

    def test_a_pictured_map_draws_only_the_picture_outline(self):
        data = dict(SMALL, ground=[[[0, 0], [50, 0], [50, 50]]], pictured=True)
        shape = layout(data, 400, 200)
        self.assertEqual(shape["lines"], [])
        self.assertEqual(shape["circles"], [])
        self.assertTrue(shape["ground"])
        self.assertTrue(shape["markers"])
        plain = layout(dict(SMALL, ground=data["ground"]), 400, 200)
        self.assertTrue(plain["lines"] and plain["circles"])

    def test_shipped_ground_stays_inside_the_map(self):
        import json
        from pathlib import Path
        found = 0
        for path in sorted((Path(__file__).resolve().parent.parent / "maps" / "settlements").glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for outline in data.get("ground", []):
                found += 1
                self.assertGreaterEqual(len(outline), 3, path.name)
                for x, y in outline:
                    self.assertTrue(-5 <= x <= data["size"][0] + 5 and -5 <= y <= data["size"][1] + 5, (path.name, x, y))
        self.assertGreaterEqual(found, 2)


class CutOffPads(unittest.TestCase):
    """A picture that cuts a landing pad off: the map reaches past the edge and the rest of the pad is drawn there (Ben, 15 Nov 2026)."""

    def test_bounds_default_to_the_picture(self):
        self.assertEqual(settlement_maps.bounds({"size": [200, 100]}), (0.0, 0.0, 200.0, 100.0))

    def test_bounds_that_do_not_cover_the_picture_are_ignored(self):
        self.assertEqual(settlement_maps.bounds({"size": [200, 100], "bounds": [10, 0, 150, 100]}), (0.0, 0.0, 200.0, 100.0))
        self.assertEqual(settlement_maps.bounds({"size": [200, 100], "bounds": "junk"}), (0.0, 0.0, 200.0, 100.0))

    def test_a_longer_map_keeps_its_points_in_the_right_place(self):
        data = {"id": "x", "size": [200, 100], "bounds": [0, 0, 200, 300]}
        project, _ = settlement_maps.projector(data, 200, 300)
        self.assertEqual(project(100, 150), (100.0, 150.0))            # the middle of the whole area
        self.assertEqual(project(0, 0), (0.0, 0.0))

    def test_only_the_part_outside_the_picture_is_drawn(self):
        data = {"id": "x", "size": [200, 100], "bounds": [0, 0, 200, 200], "pad_outlines": [{"x": 100, "y": 100, "half": 40, "facing": 0}]}
        pieces = settlement_maps.pad_outline_pieces(data)
        self.assertTrue(pieces)
        for x1, y1, x2, y2 in pieces:
            self.assertGreater((y1 + y2) / 2.0, 100)

    def test_nothing_is_drawn_beyond_the_bounds_and_bad_pads_are_skipped(self):
        data = {"id": "x", "size": [200, 100], "pad_outlines": [{"x": 100, "y": 150, "half": 40}, {"x": "a"}]}
        self.assertEqual(settlement_maps.pad_outline_pieces(data), [])

    def test_the_cut_off_maps_ship_in_the_game_files(self):
        from pathlib import Path
        for name in ("agriculture_4", "extraction_2", "industrial_4"):
            data = json.loads((Path(__file__).resolve().parent.parent / "maps" / "settlements" / (name + ".json")).read_text(encoding="utf-8"))
            self.assertTrue(settlement_maps.pad_outline_pieces(data), name)
            x0, y0, x1, y1 = settlement_maps.bounds(data)
            self.assertLessEqual(max(-y0, y1 - data["size"][1]), 400, name)         # the overlay must not shrink the map too much


class PadSizes(unittest.TestCase):
    """Landing pads are drawn at the wiki's real size: Large 213 m x 128 m, Medium 150 x 90, Small 66 x 55."""

    def test_a_large_pad_is_213_by_128_metres(self):
        c = settlement_maps.pad_corners({"x": 500, "y": 500, "size": "Large", "facing": 0}, 0.5)       # 0.5 m per unit
        sides = sorted({round(math.hypot(c[i][0] - c[(i + 1) % 4][0], c[i][1] - c[(i + 1) % 4][1])) for i in range(4)})
        self.assertEqual(sides, [256, 426])                       # 128 m and 213 m in map units

    def test_the_long_side_runs_the_way_the_ship_faces(self):
        east = settlement_maps.pad_corners({"x": 0, "y": 0, "size": "Large", "facing": 90}, 1.0)
        xs = [p[0] for p in east]
        ys = [p[1] for p in east]
        self.assertAlmostEqual(max(xs) - min(xs), 213.0, places=3)
        self.assertAlmostEqual(max(ys) - min(ys), 128.0, places=3)

    def test_the_maps_own_scale_sets_the_size(self):
        a = settlement_maps.pad_corners({"x": 0, "y": 0, "size": "Medium", "facing": 0, "scale": 0.3})
        self.assertAlmostEqual(max(p[1] for p in a) - min(p[1] for p in a), 150 / 0.3, places=3)

    def test_the_three_cut_off_maps_use_the_real_pad_size(self):
        from pathlib import Path
        for name in ("agriculture_4", "extraction_2", "industrial_4"):
            data = json.loads((Path(__file__).resolve().parent.parent / "maps" / "settlements" / (name + ".json")).read_text(encoding="utf-8"))
            self.assertEqual(data["pad_outlines"][0]["size"], "Large", name)
            self.assertNotIn("half", data["pad_outlines"][0], name)
