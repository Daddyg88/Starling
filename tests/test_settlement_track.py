import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from control.settlement_voice import SettlementMapVoice
from navigation import settlement_track
from navigation.settlement_maps import MapView, SettlementMaps
from navigation.settlement_track import SettlementTracker, feature_of, fit, map_points, world_xy

# real numbers from a visit to Shi Construction (Industrial 2), 2026-11-09
RADIUS = 1074442.625
APPROACH = {"event": "ApproachSettlement", "Name": "Shi Construction", "MarketID": 4365483779, "StationEconomy": "$economy_Industrial;",
            "Latitude": 50.642288, "Longitude": -110.657997}
DOCKING = {"event": "DockingRequested", "LandingPads": {"Small": 0, "Medium": 0, "Large": 1}}
SHIP = (50.645607, -110.662483)
ALARM = (50.634216, -110.657135)
POWER = (50.635338, -110.663132)
TERMINALS = [((50.641743, -110.668892), (1180, 188)), ((50.639, -110.653786), (869, 630)), ((50.640373, -110.651436), (897, 737))]


def here(lat, lon, heading=0.0):
    return {"lat": lat, "lon": lon, "heading": heading, "radius": RADIUS}


class Setup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = SimpleNamespace(latitude=SHIP[0], longitude=SHIP[1], heading=0.0, planet_radius=RADIUS, status_flags2=0)
        self.maps = SettlementMaps()
        # only the Industrial 2 layout, so the real-visit numbers match one map (the shipped set has several Industrial maps with one large pad)
        self.maps.maps = {"industrial_2": self.maps.get("industrial_2")}
        self.view = MapView()
        self.path = Path(self.tmp.name) / "cal.json"
        self.tracker = SettlementTracker(lambda: self.state, self.maps, self.view, self.path)

    def arrive(self):
        self.tracker.on_entry(dict(APPROACH))
        self.tracker.on_entry(dict(DOCKING))
        self.tracker.on_entry({"event": "Docked", "StationType": "OnFootSettlement", "LandingPads": DOCKING["LandingPads"]})

    def calibrate(self):
        self.arrive()
        self.tracker.on_mark("alarms", here(*ALARM))
        return self.tracker.on_mark("power regulator", here(*POWER))


class Recognising(Setup):
    def test_group_and_pad_counts_pick_the_map(self):
        self.tracker.on_entry(dict(APPROACH))
        self.assertIsNone(self.tracker.suggestion())              # pads not known yet
        self.tracker.on_entry(dict(DOCKING))
        self.assertEqual(self.tracker.suggestion(), "industrial_2")

    def test_several_layouts_with_the_same_pads_suggest_nothing(self):
        self.tracker.maps = SettlementMaps()      # the whole shipped set
        self.tracker.on_entry(dict(APPROACH))
        self.tracker.on_entry(dict(DOCKING))
        self.assertIsNone(self.tracker.suggestion())
        self.assertGreater(len(self.tracker.candidates()), 1)

    def test_wrong_pad_counts_suggest_nothing(self):
        self.tracker.on_entry(dict(APPROACH))
        self.tracker.on_entry({"event": "DockingRequested", "LandingPads": {"Small": 2, "Medium": 2, "Large": 0}})
        self.assertIsNone(self.tracker.suggestion())

    def test_an_unknown_economy_suggests_nothing(self):
        self.tracker.on_entry(dict(APPROACH, StationEconomy="$economy_Colony;"))
        self.tracker.on_entry(dict(DOCKING))
        self.assertIsNone(self.tracker.suggestion())

    def test_leaving_forgets_the_settlement(self):
        self.arrive()
        self.tracker.on_entry({"event": "SupercruiseEntry"})
        self.assertIsNone(self.tracker.suggestion())


class Lining_up(Setup):
    def test_the_real_marks_fit_the_map_closely(self):
        points = map_points(self.maps.get("industrial_2"))
        self.assertEqual(set(points), {"power", "alarm", "pad"})
        east_north = lambda p: world_xy(p[0], p[1], APPROACH["Latitude"], APPROACH["Longitude"], RADIUS)
        a, t, rms = fit([(points["alarm"], east_north(ALARM)), (points["power"], east_north(POWER)), (points["pad"], east_north(SHIP))])
        self.assertLess(rms, 4.0)                                  # the three independent spots agree to a few metres
        self.assertTrue(0.28 <= abs(a) <= 0.36)                    # metres per map unit

    def test_two_marks_line_the_map_up_and_it_is_saved(self):
        self.arrive()
        self.assertIn("Now mark", self.tracker.on_mark("alarms", here(*ALARM)))
        said = self.tracker.on_mark("power regulator", here(*POWER))
        self.assertIn("lined up", said)
        self.assertIn("landing pad", said)                          # the ship's pad agreed, so it was used as a check
        self.assertIn("4365483779", self.tracker.saved)
        again = SettlementTracker(lambda: self.state, self.maps, MapView(), self.path)
        again.on_entry(dict(APPROACH))                              # next visit: nothing to do
        self.assertIsNotNone(again.calibration)
        self.assertEqual(again.suggestion(), "industrial_2")

    def test_you_are_where_you_stand_and_face_the_right_way(self):
        self.calibrate()
        data = self.maps.get("industrial_2")
        points = map_points(data)
        for spot, name in ((ALARM, "alarm"), (POWER, "power")):
            self.state.latitude, self.state.longitude = spot
            self.tracker.on_status(self.state)
            self.assertLess(math.hypot(self.view.position["x"] - points[name][0], self.view.position["y"] - points[name][1]), 30)
        for spot, px in TERMINALS:                                 # terminals marked earlier (not used for the fit) land near real terminals
            self.state.latitude, self.state.longitude = spot
            self.tracker.on_status(self.state)
            self.assertLess(math.hypot(self.view.position["x"] - px[0], self.view.position["y"] - (px[1] - 160)), 60)

    def test_the_arrow_points_the_way_you_face(self):
        self.calibrate()
        east, north = world_xy(ALARM[0], ALARM[1], *POWER, RADIUS)           # walking from the power regulator to the alarm console
        heading = math.degrees(math.atan2(east, north))
        points = map_points(self.maps.get("industrial_2"))
        dx, dy = points["alarm"][0] - points["power"][0], points["alarm"][1] - points["power"][1]
        wanted = math.degrees(math.atan2(dx, -dy)) % 360          # screen angle clockwise from up
        got = self.tracker.calibration.arrow_angle(heading)
        self.assertLess(abs((got - wanted + 180) % 360 - 180), 4)

    def test_far_from_the_settlement_there_is_no_position(self):
        self.calibrate()
        self.state.latitude += 0.5
        self.tracker.on_status(self.state)
        self.assertIsNone(self.view.position)

    def test_marks_too_close_together_are_refused(self):
        self.arrive()
        self.tracker.on_mark("alarms", here(*ALARM))
        said = self.tracker.on_mark("power regulator", here(ALARM[0] + 0.00001, ALARM[1]))
        self.assertIn("too close", said)
        self.assertIsNone(self.tracker.calibration)

    def test_spots_of_the_wrong_size_are_refused(self):
        self.arrive()
        self.tracker.on_mark("alarms", here(*ALARM))
        said = self.tracker.on_mark("power regulator", here(ALARM[0] - 0.02, ALARM[1]))        # 375 m away is far too big for this map
        self.assertIn("wrong size", said)
        self.assertIsNone(self.tracker.calibration)

    def test_reset_by_voice_forgets_it(self):
        self.calibrate()
        self.assertIn("reset", self.tracker.try_handle("reset the settlement map"))
        self.assertIsNone(self.tracker.calibration)
        self.assertNotIn("4365483779", self.tracker.saved)
        self.assertIsNone(self.tracker.try_handle("show the settlement map"))

    def test_marking_without_a_settlement_or_for_other_spots_does_nothing(self):
        self.assertIsNone(self.tracker.on_mark("power regulator", here(*POWER)))
        self.arrive()
        self.assertIsNone(self.tracker.on_mark("coffee machine", here(*POWER)))

    def test_feature_names(self):
        self.assertEqual(feature_of("power regulator"), "power")
        self.assertEqual(feature_of("alarms"), "alarm")
        self.assertEqual(feature_of("alarm console"), "alarm")
        self.assertEqual(feature_of("terminal"), "terminal")
        self.assertEqual(feature_of("airlock"), "entry")
        self.assertIsNone(feature_of("coffee machine"))


class Voice(Setup):
    def test_show_the_settlement_map_with_no_name_uses_the_one_she_worked_out(self):
        voice = SettlementMapVoice(self.maps, self.view, suggest=self.tracker.suggestion)
        self.assertIn("Which settlement map", voice.try_handle("show settlement map"))
        self.arrive()
        self.assertIn("Industrial 2", voice.try_handle("show settlement map"))
        self.assertEqual(self.view.current, "industrial_2")
        voice.maps = SettlementMaps()             # naming a layout works for any shipped map
        self.assertIn("Tourist 1", voice.try_handle("show settlement map tourist one"))


if __name__ == "__main__":
    unittest.main()


T1, T2, T3 = (50.641743, -110.668892), (50.639, -110.653786), (50.640373, -110.651436)       # three terminals at Shi Construction


class Helpers(Setup):
    def terminals(self, count=3):
        said = None
        for lat, lon in (T1, T2, T3)[:count]:
            said = self.tracker.on_mark("terminal", here(lat, lon))
        return said

    def walk(self, lat, lon, on_foot=True, heading=90.0):
        self.state.latitude, self.state.longitude, self.state.heading = lat, lon, heading
        self.state.status_flags2 = 1 if on_foot else 0
        self.tracker.on_status(self.state)

    def ready(self):
        self.arrive()
        self.terminals()
        self.walk(*SHIP, on_foot=False)


class WithoutPowerOrAlarm(Helpers):
    """The map lines itself up from terminals alone: nobody has to visit the power regulator or the alarm."""

    def test_three_terminals_line_the_map_up(self):
        self.arrive()
        self.terminals()
        cal = self.tracker.calibration
        self.assertIsNotNone(cal)
        self.assertEqual(cal.map_id, "industrial_2")
        self.assertAlmostEqual(cal.turn_degrees(), 111, delta=8)

    def test_two_terminals_are_not_enough_and_she_says_so(self):
        self.arrive()
        said = self.terminals(2)
        self.assertIsNone(self.tracker.calibration)
        self.assertIn("more", said)

    def test_an_opened_terminal_screen_counts_without_saying_anything(self):
        self.arrive()
        for lat, lon in (T1, T2, T3):
            self.state.latitude, self.state.longitude, self.state.status_flags2, self.state.gui_focus = lat, lon, 1, 0
            self.tracker.on_status(self.state)
            self.state.gui_focus = 5
            self.tracker.on_status(self.state)
        self.assertIsNotNone(self.tracker.calibration)
        self.assertEqual(self.tracker.suggestion(), "industrial_2")

    def test_a_screen_that_stays_open_is_one_spot(self):
        self.arrive()
        self.state.latitude, self.state.longitude, self.state.status_flags2, self.state.gui_focus = T1[0], T1[1], 1, 5
        for _ in range(5):
            self.tracker.on_status(self.state)
        self.assertEqual(len([s for s in self.tracker.spots if s[0] == "terminal"]), 1)

    def test_it_is_remembered_for_next_time(self):
        self.arrive()
        self.terminals()
        again = SettlementTracker(lambda: self.state, self.maps, MapView(), self.path)
        again.on_entry(dict(APPROACH))
        self.assertIsNotNone(again.calibration)


class ShowingAndHiding(Helpers):
    def test_the_map_comes_up_when_you_step_out(self):
        self.ready()
        self.assertIsNone(self.view.current)
        self.walk(*SHIP)
        self.assertEqual(self.view.current, "industrial_2")

    def test_it_goes_when_you_get_back_in_the_ship(self):
        self.ready()
        self.walk(*SHIP)
        self.walk(*SHIP, on_foot=False)
        self.assertIsNone(self.view.current)

    def test_it_is_north_up_and_the_arrow_is_your_heading(self):
        self.ready()
        self.walk(*SHIP, heading=90.0)
        self.assertAlmostEqual(self.view.turn, 111, delta=8)
        self.assertEqual(self.view.position["angle"], 90.0)

    def test_hiding_it_by_voice_keeps_it_hidden(self):
        self.ready()
        voice = SettlementMapVoice(self.maps, self.view, suggest=self.tracker.suggestion, dismissed=self.tracker.set_dismissed)
        self.walk(*SHIP)
        voice.try_handle("hide the settlement map")
        self.walk(*SHIP)
        self.assertIsNone(self.view.current)
        voice.try_handle("show the settlement map")
        self.walk(*SHIP)
        self.assertEqual(self.view.current, "industrial_2")

    def test_it_is_not_shown_far_from_the_settlement(self):
        self.ready()
        self.walk(SHIP[0] + 0.05, SHIP[1])
        self.assertIsNone(self.view.current)

    def test_a_map_you_opened_yourself_is_not_taken_down(self):
        self.ready()
        self.view.current = "industrial_2"
        self.walk(*SHIP, on_foot=False)
        self.assertEqual(self.view.current, "industrial_2")

    def test_leaving_the_settlement_takes_the_map_down(self):
        self.ready()
        self.walk(*SHIP)
        self.tracker.on_entry({"event": "SupercruiseEntry"})
        self.assertIsNone(self.view.current)


class ThePointer(Helpers):
    def setUp(self):
        super().setUp()
        self.ready()
        self.walk(*SHIP, heading=0.0)

    def test_find_the_power_plant(self):
        said = self.tracker.try_handle("find the power plant")
        self.assertIn("power regulator", said)
        self.assertIn("metres", said)
        self.assertEqual(self.view.target["label"], "power regulator")
        self.assertAlmostEqual(self.view.target["x"], 771, delta=1)

    def test_nearest_terminal_picks_the_closest_one(self):
        self.walk(*T1)
        self.tracker.try_handle("where is the nearest terminal")
        t = self.view.target
        near = min(((m["x"], m["y"]) for m in self.maps.get("industrial_2")["markers"] if m["type"].startswith("terminal")),
                   key=lambda p: math.hypot(p[0] - self.view.position["x"], p[1] - self.view.position["y"]))
        self.assertEqual((t["x"], t["y"]), near)

    def test_the_arrow_goes_away_when_you_arrive(self):
        self.tracker.try_handle("find the alarm")
        self.assertIsNotNone(self.view.target)
        self.view.target = {"x": self.view.position["x"] + 3, "y": self.view.position["y"], "label": "alarm console"}     # a few metres away
        self.walk(*SHIP)
        self.assertIsNone(self.view.target)

    def test_stop_pointing(self):
        self.tracker.try_handle("find the power plant")
        self.assertEqual(self.tracker.try_handle("stop pointing"), "Arrow off.")
        self.assertIsNone(self.view.target)

    def test_where_is_my_ship(self):
        self.walk(*T2)
        self.assertIn("ship", self.tracker.try_handle("where is my ship"))
        self.assertIsNotNone(self.view.target)

    def test_not_lined_up_yet_she_says_so(self):
        self.tracker.calibration = None
        self.tracker.view.position = None
        self.assertIn("cannot place you", self.tracker.try_handle("find the power plant"))

    def test_other_talk_is_left_alone(self):
        self.assertIsNone(self.tracker.try_handle("what is the weather"))
        self.assertIsNone(self.tracker.try_handle("find the nearest station"))

    def test_nothing_in_the_ship(self):
        self.walk(*SHIP, on_foot=False)
        self.assertIsNone(self.tracker.try_handle("find the power plant"))
