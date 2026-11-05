import tempfile
import unittest
from pathlib import Path

from control.route_map_voice import RouteMapVoice
from journal.game_state import GameState
from navigation import galaxy_map as gm
from navigation.route import RouteFollower
from navigation.spansh import Spansh
from ui import route_overlay as ro


class Settings:
    def __init__(self, **values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


def follower_with(steps, index=0):
    folder = tempfile.mkdtemp()
    f = RouteFollower(None, Settings(), None, lambda: None, save_path=Path(folder) / "r.json", copier=lambda t: True)
    f.set_route(steps, "Colonia")
    f.index = index
    return f


class Pure(unittest.TestCase):
    def test_scene_for_test_route(self):
        steps = gm.test_route()
        scene = gm.build_scene(steps, 1, (0, 0, 0), "Colonia", 10, 6, 300)
        self.assertTrue(scene["has_route"])
        self.assertEqual(len(scene["background"]), 300)
        self.assertEqual(len(scene["background"][0]), 300)
        self.assertTrue(scene["lines"] and scene["dots"] and scene["text"])
        self.assertTrue(any("straight" in t for t, _ in scene["text"]))

    def test_no_positions_is_no_route(self):
        steps = [{"system": "A", "neutron": True, "jumps": 2}, {"system": "B", "neutron": False, "jumps": 1}]
        self.assertFalse(gm.build_scene(steps, 0, None, "B", 3, 1, 240)["has_route"])

    def test_straight_route_is_good_and_winding_is_not(self):
        straight = gm.route_points([{"system": str(i), "x": i * 1000, "y": 0, "z": 0, "neutron": True, "jumps": 1} for i in range(5)])
        self.assertEqual(gm.route_stats(straight)["verdict"], "Good route")
        bendy = gm.route_points([{"system": "a", "x": 0, "y": 0, "z": 0}, {"system": "b", "x": 5000, "y": 0, "z": 0},
                                 {"system": "c", "x": 0, "y": 0, "z": 100}])
        self.assertNotEqual(gm.route_stats(bendy)["verdict"], "Good route")

    def test_placement_and_text(self):
        x, y = ro.placement(1920, 1080, 300, 400, 2, 10)
        self.assertEqual((x, y), (1581, 108))
        self.assertEqual(ro.fit_text("abcdefghij", 5), "abcd…")
        self.assertEqual(ro.map_size("nope"), 300)


class Gating(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.active = follower_with(gm.test_route())

    def test_modes(self):
        s = Settings(**{"overlay.route_map": "route"})
        self.assertEqual(ro.wanted_mode(s, self.state, self.active), "route")
        self.assertIsNone(ro.wanted_mode(s, self.state, follower_with([])))
        self.assertEqual(ro.wanted_mode(Settings(**{"overlay.route_map": "always"}), self.state, follower_with([])), "empty")
        self.assertIsNone(ro.wanted_mode(Settings(**{"overlay.route_map": "off"}), self.state, self.active))

    def test_hidden_quit_and_screens(self):
        s = Settings()
        self.state.route_map_hidden = True
        self.assertIsNone(ro.wanted_mode(s, self.state, self.active))
        self.state.route_map_hidden = False
        self.state.game_quit = True
        self.assertIsNone(ro.wanted_mode(s, self.state, self.active))
        self.state.game_quit = False
        self.state.gui_focus = 6
        self.assertIsNone(ro.wanted_mode(s, self.state, self.active))
        self.assertEqual(ro.wanted_mode(Settings(**{"overlay.route_cockpit_only": False}), self.state, self.active), "route")

    def test_test_mode_wins(self):
        self.assertEqual(ro.wanted_mode(Settings(**{"overlay.route_map": "off"}), self.state, None, test_until=100.0, now=50.0), "test")
        self.assertIsNone(ro.wanted_mode(Settings(**{"overlay.route_map": "off"}), self.state, None, test_until=100.0, now=150.0))

    def test_scene_real_and_test(self):
        self.state.star_pos = (0.0, 0.0, 0.0)
        scene = ro.route_scene(Settings(), self.state, self.active)
        self.assertTrue(scene["has_route"])
        self.assertTrue(ro.route_scene(Settings(), self.state, None, test_until=100.0, now=1.0)["has_route"])

    def test_route_without_positions_says_so(self):
        steps = [{"system": "A", "neutron": True, "jumps": 2}, {"system": "B", "neutron": False, "jumps": 1}]
        scene = ro.route_scene(Settings(), self.state, follower_with(steps))
        self.assertIn("plot the route again", scene["text"][1][0])


class Positions(unittest.TestCase):
    def test_spansh_rows_keep_xyz(self):
        out = Spansh._waypoints({"system_jumps": [
            {"system": "Sol", "x": 0, "y": 0, "z": 0, "jumps": 0, "neutron_star": False},
            {"system": "B", "x": "10.5", "y": 2, "z": 3, "jumps": 4, "neutron_star": True},
            {"system": "C", "jumps": 1}]})
        self.assertEqual((out[1]["x"], out[1]["z"]), (10.5, 3.0))
        self.assertNotIn("x", out[2])

    def test_backfill(self):
        steps = [{"system": "A", "neutron": True, "jumps": 2}, {"system": "B", "neutron": False, "jumps": 1, "x": 1, "y": 1, "z": 1}]
        f = follower_with(steps)
        asked = []

        def lookup(name):
            asked.append(name)
            return (5.0, 6.0, 7.0)
        self.assertEqual(ro.backfill_positions(f, lookup, sleep=lambda s: None), 1)
        self.assertEqual(asked, ["A"])
        self.assertEqual(f.waypoints[0]["z"], 7.0)


class Voice(unittest.TestCase):
    def test_hide_and_show(self):
        state = GameState()
        said = []

        class N:
            def say(self, key, fields=None):
                said.append(key)
        v = RouteMapVoice(lambda: state, N())
        self.assertTrue(v.try_handle("hide the route map"))
        self.assertTrue(state.route_map_hidden)
        self.assertTrue(v.try_handle("show the route map"))
        self.assertFalse(state.route_map_hidden)
        self.assertEqual(said, ["RouteMap_Hidden", "RouteMap_Shown"])

    def test_leaves_game_commands_alone(self):
        v = RouteMapVoice(lambda: GameState())
        for text in ("open the galaxy map", "show me the route on the galaxy map", "plot a neutron route", "clear the route", "hide the bio overlay"):
            self.assertIsNone(v.try_handle(text), text)

    def test_lines_exist(self):
        import json
        data = json.load(open("voicepacks/default/routemap.json", encoding="utf-8"))
        self.assertEqual(sorted(data), ["RouteMap_Hidden", "RouteMap_Shown"])


if __name__ == "__main__":
    unittest.main()


class RouteMapLook(unittest.TestCase):
    def test_see_through_with_orange_regions_yellow_waypoints_cyan_route(self):
        steps = gm.test_route()
        scene = gm.build_scene(steps, 1, (steps[0]["x"], steps[0]["y"], steps[0]["z"]), "Colonia", 3, 5, 300)
        pixels = {c for row in scene["background"] for c in row}
        self.assertEqual(pixels, {gm.KEY, gm.ORANGE})          # nothing coloured per region any more
        small = {c for row in scene["inset"]["background"] for c in row}
        self.assertTrue(small <= {gm.KEY, gm.ORANGE})
        colours = {line[4] for line in scene["lines"]}
        self.assertIn(gm.AHEAD, colours)
        self.assertTrue(colours <= {gm.AHEAD, gm.BEHIND})
        self.assertEqual(gm.AHEAD, "#35e0ff")
        yellow = {dot[3] or dot[4] for dot in scene["dots"]}
        self.assertIn(gm.WAYPOINT, yellow)
        self.assertTrue(all(colour for colour in {t[1] for t in scene["text"]}) and {t[1] for t in scene["text"]} == {gm.ORANGE})
