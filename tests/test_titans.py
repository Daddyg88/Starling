"""Thargoid Titans: the commands, the 1000 light year rule, the war story on the way and the fate on the last jump."""

import json
import unittest
from pathlib import Path

from core.event_bus import Event
from navigation import titans
from tests import test_neutron
from tests.test_guardian import Spansh

TITANS = titans.load()


class Parse(unittest.TestCase):
    def test_phrases(self):
        thor = next(t for t in TITANS if t.name == "Thor")
        cocijo = next(t for t in TITANS if t.name == "Cocijo")
        cases = [("plot me a route to the nearest titan", ("nearest", "go")),
                 ("take me to the closest titan", ("nearest", "go")),
                 ("plot a route to titan thor", (thor, "go")),
                 ("take me to thor", (thor, "go")),
                 ("route to co see yo", (cocijo, "go")),
                 ("where is the titan cocijo", (cocijo, "where")),
                 ("tell me about cocijo", (cocijo, "story")),
                 ("what happened to titan thor", (thor, "story"))]
        for text, expected in cases:
            self.assertEqual(titans.parse(TITANS, text), expected, text)
        for text in ("plot a route to colonia", "take me to felicity farseer", "tell me about the thargoid war", "thorough"):
            self.assertIsNone(titans.parse(TITANS, text), text)

    def test_all_eight(self):
        self.assertEqual(sorted(t.order for t in TITANS), list(range(1, 9)))
        for t in TITANS:
            self.assertIs(titans.find(TITANS, t.name.lower()), t)


class Go(unittest.TestCase):
    build = test_neutron.VoiceTests.build
    keys = test_neutron.VoiceTests.keys

    def setup_voice(self, coords=None, system="Sol"):
        v = self.build(system=system, spansh=Spansh(coords))
        self.state.star_pos = (0.0, 0.0, 0.0)
        self.macro = []
        v.plot_macro = lambda s: self.macro.append(s) or (True, "")
        return v

    def test_nearest_titan_is_the_closest_one(self):
        coords = {"Hyades Sector FB-N b7-6": (0.0, 0.0, 600.0), "HIP 8887": (0.0, 0.0, 3000.0), "Col 285 Sector IG-O c6-5": (0.0, 0.0, 50.0)}
        v = self.setup_voice(coords)
        v.try_handle("plot me a route to the nearest titan")
        self.assertEqual(self.macro, ["Col 285 Sector IG-O c6-5"])
        self.assertEqual(self.keys(), ["TitanNear"])
        self.assertEqual(v.titan_goal.name, "Thor")

    def test_nearest_without_coordinates_asks_which(self):
        v = self.setup_voice({})
        v.try_handle("take me to the nearest titan")
        self.assertEqual(self.keys(), ["TitanNearestUnknown"])
        self.assertIsNone(v.titan_goal)

    def test_far_titan_uses_a_neutron_route(self):
        v = self.setup_voice({"HIP 8887": (0.0, 0.0, 5000.0)})
        v.try_handle("take me to titan leigong")
        self.assertEqual(self.macro, [])
        self.assertEqual(self.keys()[0], "TitanFar")
        self.assertEqual(v.titan_goal.name, "Leigong")

    def test_the_story_is_told_a_piece_per_jump_and_the_fate_on_arrival(self):
        v = self.setup_voice({"Col 285 Sector IG-O c6-5": (0.0, 0.0, 50.0)})
        v.try_handle("take me to titan thor")
        self.narr.said.clear()
        now = [0.0]
        v.clock = lambda: now[0]
        for system in ("A", "B", "C", "D"):
            now[0] += 50
            v.on_arrival(Event("FSDJump", {"StarSystem": system}))
        self.assertEqual(self.keys(), ["TitanTour_War_1", "TitanTour_War_2", "TitanTour_Intro_Thor", "TitanTour_War_3"])
        now[0] += 1
        v.on_arrival(Event("FSDJump", {"StarSystem": "Col 285 Sector IG-O c6-5"}))
        self.assertEqual(self.keys()[-1], "TitanArrive_Thor")
        self.assertIsNone(v.titan_goal)

    def test_pieces_are_spaced_out(self):
        v = self.setup_voice({"Col 285 Sector IG-O c6-5": (0.0, 0.0, 50.0)})
        v.try_handle("take me to thor")
        self.narr.said.clear()
        v.clock = lambda: 100.0
        for system in ("A", "B", "C"):
            v.on_arrival(Event("FSDJump", {"StarSystem": system}))
        self.assertEqual(self.keys(), ["TitanTour_War_1"])

    def test_switch_off_keeps_the_story_quiet_but_not_the_arrival(self):
        v = self.setup_voice({"Col 285 Sector IG-O c6-5": (0.0, 0.0, 50.0)})
        v.settings.set("titans.talk", False)
        v.try_handle("take me to thor")
        self.narr.said.clear()
        v.clock = lambda: 1000.0
        v.on_arrival(Event("FSDJump", {"StarSystem": "A"}))
        self.assertEqual(self.keys(), [])
        v.on_arrival(Event("FSDJump", {"StarSystem": "Col 285 Sector IG-O c6-5"}))
        self.assertEqual(self.keys(), ["TitanArrive_Thor"])

    def test_a_different_destination_stops_the_story(self):
        v = self.setup_voice({"Col 285 Sector IG-O c6-5": (0.0, 0.0, 50.0)})
        v.try_handle("take me to thor")
        v.try_handle("plot a neutron route to Colonia")
        self.assertIsNone(v.titan_goal)

    def test_the_fate_on_request(self):
        v = self.setup_voice()
        v.try_handle("what happened to cocijo")
        self.assertEqual(self.keys(), ["TitanArrive_Cocijo"])


class Data(unittest.TestCase):
    def test_every_titan_has_its_lines(self):
        pack = json.loads(Path("voicepacks/default/titans.json").read_text(encoding="utf-8"))
        for t in TITANS:
            self.assertIn("TitanTour_Intro_" + t.name, pack)
            self.assertIn("TitanArrive_" + t.name, pack)
        for n in range(1, 9):
            self.assertIn("TitanTour_War_%d" % n, pack)
        for key in ("TitanNear", "TitanFar", "TitanFarUnknown", "TitanHere", "TitanPlotOff", "TitanWhere", "TitanNearestUnknown", "TitanArrive"):
            self.assertIn(key, pack)


if __name__ == "__main__":
    unittest.main()
