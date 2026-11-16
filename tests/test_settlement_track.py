import cmath
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
        self.tracker.shipped = {}
        self.tracker.known = {}                    # (the shipped list of certain settlements is tested on its own)
        self.tracker.pad_frames = {}               # (the pad arrows are tested on their own, so the other tests see no landing line-up)

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
        self.assertTrue(self.tracker.saved["4365483779"].get("disabled"))              # remembered as reset, so the shipped one is not put back
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
        if count >= 3:
            said = self.tracker.on_mark("power regulator", here(*POWER))          # a fourth spot: four are needed
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

    def test_three_terminals_and_the_power_regulator_line_the_map_up(self):
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

    def stand(self, lat, lon, seconds, clock):
        """Stand still on foot for `seconds`, with a Status reading every second."""
        self.state.latitude, self.state.longitude, self.state.status_flags2 = lat, lon, 1
        for _ in range(int(seconds) + 1):
            self.tracker.on_status(self.state)
            clock[0] += 1.0

    def test_standing_still_at_four_places_lines_the_map_up(self):
        clock = [100.0]
        self.tracker.clock = lambda: clock[0]
        self.arrive()
        self.state.latitude, self.state.longitude, self.state.status_flags2 = SHIP[0], SHIP[1], 1
        self.tracker.on_status(self.state)                                  # stepping out of the ship
        for lat, lon in (T1, T2, T3, POWER):
            self.stand(lat, lon, 8, clock)
        self.assertIsNotNone(self.tracker.calibration)
        self.assertEqual(self.tracker.suggestion(), "industrial_2")

    def test_standing_still_at_just_three_places_is_enough_with_the_known_map_size(self):
        clock = [100.0]
        self.tracker.clock = lambda: clock[0]
        self.arrive()
        self.state.latitude, self.state.longitude, self.state.status_flags2 = SHIP[0], SHIP[1], 1
        self.tracker.on_status(self.state)
        for lat, lon in (T1, T2, T3):
            self.stand(lat, lon, 8, clock)
        self.assertIsNotNone(self.tracker.calibration)
        self.assertEqual(self.tracker.suggestion(), "industrial_2")

    def test_two_stops_and_your_ship_are_still_not_enough(self):
        clock = [100.0]
        self.tracker.clock = lambda: clock[0]
        self.arrive()
        self.tracker.on_mark("pad", here(*SHIP))
        for lat, lon in (T1, T2):
            self.stand(lat, lon, 8, clock)
        self.assertIsNone(self.tracker.calibration)

    def three_stop_lineup(self):
        clock = [100.0]
        self.tracker.clock = lambda: clock[0]
        self.arrive()
        self.state.latitude, self.state.longitude, self.state.status_flags2 = SHIP[0], SHIP[1], 1
        self.tracker.on_status(self.state)
        for lat, lon in (T1, T2, T3):
            self.stand(lat, lon, 8, clock)
        self.assertIsNotNone(self.tracker.calibration)
        return clock

    def test_a_three_stop_lineup_is_confirmed_by_two_later_stops_that_fit(self):
        clock = self.three_stop_lineup()
        self.assertTrue(self.tracker.provisional)
        self.stand(*POWER, 8, clock)
        self.assertTrue(self.tracker.provisional)
        self.stand(T1[0] + 0.0004, T1[1], 3, clock)                      # walk away, then back
        self.stand(*T1, 8, clock)
        self.assertFalse(self.tracker.provisional)
        self.assertIsNotNone(self.tracker.calibration)

    def test_one_stop_that_is_not_on_the_map_does_not_undo_it(self):
        clock = self.three_stop_lineup()
        self.stand(SHIP[0] - 0.003, SHIP[1] + 0.003, 8, clock)           # a suit recharge, say
        self.assertIsNotNone(self.tracker.calibration)

    def test_two_stops_that_do_not_fit_take_a_three_stop_lineup_back(self):
        clock = self.three_stop_lineup()
        said = []
        self.tracker.say = said.append
        self.stand(SHIP[0] - 0.003, SHIP[1] + 0.003, 8, clock)
        self.stand(SHIP[0] - 0.006, SHIP[1] - 0.003, 8, clock)
        self.assertIsNone(self.tracker.calibration)
        self.assertNotIn(self.tracker.settlement["market"], self.tracker.saved)
        self.assertTrue(any("taken it back" in text for text in said))

    def test_waiting_beside_the_ship_is_not_a_terminal(self):
        clock = [100.0]
        self.tracker.clock = lambda: clock[0]
        self.arrive()
        self.stand(SHIP[0], SHIP[1], 20, clock)
        self.assertEqual(self.tracker.spots, [s for s in self.tracker.spots if s[0] == "pad"])

    def test_one_long_stop_is_one_spot(self):
        clock = [100.0]
        self.tracker.clock = lambda: clock[0]
        self.arrive()
        self.state.latitude, self.state.longitude, self.state.status_flags2 = SHIP[0], SHIP[1], 1
        self.tracker.on_status(self.state)
        self.stand(T1[0], T1[1], 30, clock)
        self.assertEqual(len([s for s in self.tracker.spots if s[0] == "stop"]), 1)

    def test_walking_past_is_not_a_stop(self):
        clock = [100.0]
        self.tracker.clock = lambda: clock[0]
        self.arrive()
        self.state.latitude, self.state.longitude, self.state.status_flags2 = SHIP[0], SHIP[1], 1
        self.tracker.on_status(self.state)
        for step in range(20):
            self.stand(T1[0] + step * 0.0001, T1[1], 0, clock)
        self.assertEqual([s for s in self.tracker.spots if s[0] == "stop"], [])

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


class StartedLate(Setup):
    def test_a_journal_being_caught_up_still_tells_her_where_you_are(self):
        self.tracker.on_entry(dict(APPROACH), True)
        self.tracker.on_entry(dict(DOCKING), True)
        self.assertEqual(self.tracker.suggestion(), "industrial_2")
        self.assertNotIn("pad", self.tracker.anchors)             # where the ship is NOW says nothing about where it landed


class WhenSheCannotChoose(Setup):
    def test_she_lists_the_layouts_it_could_be_and_a_named_one_sticks(self):
        self.tracker.maps = SettlementMaps()
        self.tracker.on_entry({"event": "ApproachSettlement", "Name": "Some Foundry", "MarketID": 1, "StationEconomy": "$economy_Industrial;",
                               "Latitude": -24.94, "Longitude": 33.37})
        self.tracker.on_entry(dict(DOCKING))
        self.assertIsNone(self.tracker.suggestion())
        voice = SettlementMapVoice(self.tracker.maps, self.view, suggest=self.tracker.suggestion, dismissed=self.tracker.set_dismissed,
                                   options=self.tracker.options)
        said = voice.try_handle("show settlement map")
        self.assertIn("Industrial 2", said)
        self.assertIn("Industrial 5", said)
        self.assertNotIn("Industrial 3", said)               # Industrial 3 has a medium pad, not a large one
        voice.try_handle("show settlement map industrial five")
        self.assertEqual(self.tracker.suggestion(), "industrial_5")

    def test_one_large_extraction_pad_is_only_extraction_3(self):
        self.tracker.maps = SettlementMaps()
        self.tracker.on_entry({"event": "ApproachSettlement", "Name": "Cheesebeard's Cave", "MarketID": 1, "StationEconomy": "$economy_Extraction;",
                               "Latitude": -24.94, "Longitude": 33.37})
        self.tracker.on_entry(dict(DOCKING))
        self.assertEqual(self.tracker.suggestion(), "extraction_3")


class KnownSettlements(Setup):
    def test_a_settlement_we_have_walked_is_known_at_once(self):
        self.tracker.known = settlement_track.known_settlements()
        self.assertEqual(self.tracker.known.get("4365483779"), "industrial_2")
        self.tracker.maps = SettlementMaps()                          # the whole set: Industrial 2 and 5 share one large pad
        self.tracker.on_entry(dict(APPROACH))
        self.assertEqual(self.tracker.suggestion(), "industrial_2")

    def test_she_speaks_once_when_she_cannot_choose(self):
        said = []
        self.tracker.say = said.append
        self.tracker.maps = SettlementMaps()
        self.tracker.on_entry(dict(APPROACH))
        self.tracker.on_entry(dict(DOCKING))
        self.state.latitude, self.state.longitude, self.state.status_flags2 = SHIP[0], SHIP[1], 1
        self.tracker.on_status(self.state)
        self.tracker.on_status(self.state)
        self.assertEqual(len(said), 1)
        self.assertIn("Industrial 2", said[0])

    def test_the_voice_answer_is_spoken(self):
        said = []
        voice = SettlementMapVoice(self.maps, self.view, say=said.append)
        voice.try_handle("show settlement map industrial two")
        self.assertEqual(len(said), 1)


class ShippedLineUp(Setup):
    def test_shi_construction_is_lined_up_from_the_start(self):
        self.tracker.shipped = settlement_track.known_calibrations()
        self.tracker.on_entry(dict(APPROACH))
        self.assertIsNotNone(self.tracker.calibration)
        self.state.latitude, self.state.longitude, self.state.status_flags2, self.state.heading = ALARM[0], ALARM[1], 1, 20.0
        self.tracker.on_status(self.state)
        self.assertAlmostEqual(self.view.position["x"], 630, delta=40)           # standing at the alarm console
        self.assertAlmostEqual(self.view.position["y"], 290, delta=40)
        self.assertEqual(self.view.position["angle"], 20.0)


class OldSavedLineUps(Setup):
    def test_a_line_up_saved_by_an_older_version_is_not_trusted(self):
        import json
        self.path.write_text(json.dumps({"4365483779": {"map": "industrial_2", "a": [0.1, 0.3], "t": [0, 0], "ref": [50.64, -110.65], "radius": RADIUS}}))
        again = SettlementTracker(lambda: self.state, self.maps, MapView(), self.path)
        again.known = again.shipped = {}
        again.on_entry(dict(APPROACH))
        self.assertIsNone(again.calibration)


class LinedUpFromTheLanding(Setup):
    """On pad 1 the ship faces the way the layout is turned (the idea SrvSurvey uses). Real headings at Shi Construction were 251 to 265."""

    def land(self, pad=1, heading=253.0):
        self.state.heading = heading
        self.tracker.on_entry(dict(APPROACH))
        self.tracker.on_entry(dict(DOCKING))
        self.tracker.on_entry({"event": "DockingGranted", "LandingPad": pad})
        self.tracker.on_entry({"event": "Docked", "StationType": "OnFootSettlement", "LandingPads": DOCKING["LandingPads"]})

    def terminal_world(self, index):
        lat, lon = TERMINALS[index][0]
        return world_xy(lat, lon, APPROACH["Latitude"], APPROACH["Longitude"], RADIUS)

    def test_pad_one_and_a_known_frame_line_the_map_up_at_once(self):
        said = []
        self.tracker.say = said.append
        self.land()
        cal = self.tracker.calibration
        self.assertIsNotNone(cal)
        self.assertEqual(cal.meta["how"], "dock")
        self.assertTrue(self.tracker.provisional)
        self.assertAlmostEqual(abs(cal.a), 0.325, places=3)
        self.assertEqual(len(said), 1)
        # the ship's own pad lands near the pad on the picture (real heading wobble is about 8 degrees, so allow a few tens of metres)
        x, y = cal.to_map(*SHIP)
        pad = self.maps.get("industrial_2")["circles"][0]
        self.assertLess(math.hypot(x - pad["x"], y - pad["y"]) * 0.325, 40)

    def test_only_pad_one_tells_the_heading(self):
        self.land(pad=2)
        self.assertIsNone(self.tracker.calibration)

    def test_no_frame_for_the_map_means_no_guess(self):
        self.tracker.frames = {}
        self.land()
        self.assertIsNone(self.tracker.calibration)

    def test_a_different_heading_turns_the_map_the_same_amount(self):
        self.land(heading=253.0)
        first = self.tracker.calibration.turn_degrees()
        self.tracker._leave()
        self.land(heading=263.0)
        second = self.tracker.calibration.turn_degrees()
        self.assertAlmostEqual((first - second + 180) % 360 - 180, 10.0, places=3)

    def test_two_terminals_that_fit_keep_it_and_save_it(self):
        self.land()
        self.assertTrue(self.tracker.provisional)
        cal = self.tracker.calibration
        # stand exactly where the map says a terminal is
        for kind, (x, y) in [("t", p) for p in [tuple(u) for u in settlement_track.settlement_solve.features(self.maps.get("industrial_2"))["stop"][:2]]]:
            east, north = cal.t.real + (cal.a * complex(x, -y)).real, cal.t.imag + (cal.a * complex(x, -y)).imag
            self.tracker._check_stop(east, north)
        self.assertFalse(self.tracker.provisional)
        self.assertNotIn("4365483779", self.tracker.saved)         # a landing-only line-up is rough: not kept for next time (0.96.33)

    def test_two_stops_that_do_not_fit_take_it_back_and_it_is_not_tried_again(self):
        said = []
        self.tracker.say = said.append
        self.land()
        self.tracker._check_stop(900.0, 900.0)            # far outside the settlement
        self.tracker._check_stop(-900.0, 900.0)
        self.assertIsNotNone(self.tracker.calibration)    # a landing-only line-up is rough: two misses are not enough (0.96.29)
        self.tracker._check_stop(900.0, -900.0)
        self.assertIsNone(self.tracker.calibration)
        self.assertNotIn("4365483779", self.tracker.saved)
        self.assertTrue(any("taken it back" in line for line in said))
        self.tracker.on_entry({"event": "Touchdown"})
        self.assertIsNone(self.tracker.calibration)       # not guessed again at this visit


class LearningTheFrame(Setup):
    def test_a_line_up_from_your_own_marks_teaches_the_frame(self):
        self.state.heading = 253.0
        self.tracker.frames = {}
        self.tracker.on_entry(dict(APPROACH))
        self.tracker.on_entry(dict(DOCKING))
        self.tracker.on_entry({"event": "DockingGranted", "LandingPad": 1})
        self.tracker.on_entry({"event": "Docked", "StationType": "OnFootSettlement", "LandingPads": DOCKING["LandingPads"]})
        self.tracker.on_mark("alarms", here(*ALARM))
        self.tracker.on_mark("power regulator", here(*POWER))
        frame = self.tracker.frames.get("industrial_2")
        self.assertIsNotNone(frame)
        self.assertTrue(frame["learned"])
        self.assertLess(math.hypot(frame["origin"][0] - 1069, frame["origin"][1] - 432), 120)      # near what the Shi walk measured
        self.assertLess(abs(frame["offset"] - 8.7), 25)
        again = SettlementTracker(lambda: self.state, self.maps, MapView(), self.path)               # remembered for next time
        self.assertEqual(again.frames["industrial_2"]["origin"], frame["origin"])

    def test_a_line_up_without_a_pad_one_landing_teaches_nothing(self):
        self.tracker.frames = {}
        self.calibrate()                                                   # no DockingGranted line
        self.assertEqual(self.tracker.frames, {})

    def test_bad_frames_are_refused(self):
        self.assertIsNone(settlement_track.frame_problem({"origin": [1000, 400], "offset": 8.7}))
        for bad in ({}, {"origin": [1, 2]}, {"origin": ["x", 2], "offset": 1}, {"origin": [1e9, 2], "offset": 1},
                    {"origin": [1, 2], "offset": 900}, {"origin": [1, 2], "offset": 1, "scale": 50}):
            self.assertIsNotNone(settlement_track.frame_problem(bad), bad)

    def test_the_shipped_frames_are_valid(self):
        frames = settlement_track.known_frames()
        self.assertIn("industrial_2", frames)


class LinedUpFromThePadArrow(Setup):
    """0.96.23: the arrow Ben drew on a layout's landing pad gives a rough line-up from the landing, for any pad number."""

    def setUp(self):
        super().setUp()
        self.tracker.frames = {}                          # no pad-1 frame, so only the arrow can do it
        self.tracker.pad_frames = settlement_track.known_pad_frames()

    def land(self, pad=1, heading=253.0, name_it_after=False):
        self.state.heading = heading
        self.tracker.on_entry(dict(APPROACH))
        self.tracker.on_entry(dict(DOCKING))
        self.tracker.on_entry({"event": "DockingGranted", "LandingPad": pad})
        self.tracker.on_entry({"event": "Docked", "StationType": "OnFootSettlement", "LandingPads": DOCKING["LandingPads"]})

    def test_the_shipped_pad_frames_are_valid_and_cover_the_layouts(self):
        frames = settlement_track.known_pad_frames()
        self.assertGreaterEqual(len(frames), 26)
        for map_id, entry in frames.items():
            self.assertIsNone(settlement_track.pad_frame_problem(entry), map_id)
        for bad in ({"pads": [{"size": "Huge", "x": 1, "y": 1, "facing": 1}]}, {}, {"pads": "x"}, {"pads": [{"size": "Large", "x": 1, "y": 1, "facing": 400}]}, {"pads": [{"size": "Large", "x": "a", "y": 1, "facing": 1}]}):
            self.assertIsNotNone(settlement_track.pad_frame_problem(bad), bad)

    def test_it_works_for_any_pad_number_and_puts_the_ship_on_the_pad(self):
        said = []
        self.tracker.say = said.append
        self.land(pad=3)
        cal = self.tracker.calibration
        self.assertIsNotNone(cal)
        self.assertEqual(cal.meta["how"], "dock")
        self.assertTrue(self.tracker.provisional)
        x, y = cal.from_world(*self.tracker.anchors["pad"])
        pad = self.tracker.pad_frames["industrial_2"]["pads"][0]
        self.assertLess(math.hypot(x - pad["x"], y - pad["y"]), 1.0)          # the ship lands exactly on the pad's place
        self.assertEqual(len(said), 1)

    def test_the_ships_heading_turns_the_map_so_the_pad_arrow_points_that_way(self):
        self.land(heading=253.0)
        cal = self.tracker.calibration
        pad = self.tracker.pad_frames["industrial_2"]["pads"][0]
        x0, y0 = cal.from_world(*self.tracker.anchors["pad"])
        # a point 100 m ahead of the ship (compass heading 253) must lie along the arrow on the picture
        ahead = (self.tracker.anchors["pad"][0] + 100 * math.sin(math.radians(253.0)), self.tracker.anchors["pad"][1] + 100 * math.cos(math.radians(253.0)))
        x1, y1 = cal.from_world(*ahead)
        facing = math.degrees(math.atan2(x1 - x0, -(y1 - y0))) % 360
        self.assertAlmostEqual((facing - pad["facing"] + 180) % 360 - 180, 0.0, places=3)

    def test_naming_the_layout_after_landing_lines_it_up_then(self):
        self.tracker.maps = SettlementMaps()
        self.state.heading = 253.0
        self.tracker.on_entry(dict(APPROACH))
        self.tracker.on_entry(dict(DOCKING))
        self.tracker.on_entry({"event": "Docked", "StationType": "OnFootSettlement", "LandingPads": DOCKING["LandingPads"]})
        self.tracker.settlement["map"] = None
        self.tracker.calibration = None
        self.view.current = "industrial_2"
        self.tracker.set_dismissed(True)
        self.tracker.set_dismissed(False)
        self.assertEqual(self.tracker.settlement["map"], "industrial_2")
        self.assertIsNotNone(self.tracker.calibration)

    def test_a_layout_with_two_landing_pads_uses_the_pad_number(self):
        two = {"industrial_2": {"pads": [{"size": "Large", "number": 1, "x": 100, "y": 100, "facing": 0}, {"size": "Large", "number": 2, "x": 900, "y": 100, "facing": 90}]}}
        self.tracker.pad_frames = two
        self.land(pad=2)
        x, y = self.tracker.calibration.from_world(*self.tracker.anchors["pad"])
        self.assertLess(math.hypot(x - 900, y - 100), 1.0)                     # pad 2 is the second arrow
        self.tracker._leave()
        self.land(pad=1)
        x, y = self.tracker.calibration.from_world(*self.tracker.anchors["pad"])
        self.assertLess(math.hypot(x - 100, y - 100), 1.0)

    def test_two_landing_pads_and_an_unknown_pad_number_is_not_guessed(self):
        self.tracker.pad_frames = {"industrial_2": {"pads": [{"size": "Large", "number": 1, "x": 100, "y": 100, "facing": 0}, {"size": "Large", "number": 2, "x": 900, "y": 100, "facing": 90}]}}
        self.land(pad=7)
        self.assertIsNone(self.tracker.calibration)

    def test_tourist_one_has_its_pad_numbers(self):
        large = [p for p in settlement_track.known_pad_frames()["tourist_1"]["pads"] if p["size"] == "Large"]
        self.assertEqual(sorted(p["number"] for p in large), [1, 2])
        self.assertLess(min(large, key=lambda p: p["number"])["y"], max(large, key=lambda p: p["number"])["y"])      # 1 is the top pad

    def test_tourist_one_pad_three_is_the_large_pad_at_the_bottom(self):
        self.land(pad=3)
        self.tracker.settlement["map"] = self.tracker.settlement.get("map") or "tourist_1"
        pad = self.tracker._arrow_pad("tourist_1")
        self.assertEqual((pad["x"], pad["y"]), (1112, 578))
        self.tracker.settlement["pad_number"] = 7
        self.assertIsNone(self.tracker._arrow_pad("tourist_1"))                # an unseen pad number is still not guessed
        self.assertAlmostEqual(SettlementMaps().get("tourist_1")["scale"], 0.425)

    def test_tourist_one_game_pad_numbers_are_all_four(self):
        """Ben watched ships land (16 Nov 2026): bottom small = 1, top small = 2, bottom large = 3, top large = 4."""
        pads = {p["game_pad"]: (p["size"], p["y"]) for p in settlement_track.known_pad_frames()["tourist_1"]["pads"]}
        self.assertEqual(sorted(pads), [1, 2, 3, 4])
        self.assertEqual((pads[1][0], pads[2][0], pads[3][0], pads[4][0]), ("Small", "Small", "Large", "Large"))
        self.assertGreater(pads[1][1], pads[2][1])             # 1 is below 2 (a bigger y is further down the picture)
        self.assertGreater(pads[3][1], pads[4][1])
        self.land(pad=4)
        self.tracker.settlement["map"] = self.tracker.settlement.get("map") or "tourist_1"
        self.assertEqual(self.tracker._arrow_pad("tourist_1")["y"], 221)           # pad 4 = the top large pad
        self.tracker.settlement["pad_number"] = 1
        self.assertIsNone(self.tracker._arrow_pad("tourist_1"))                    # a small pad is never used as an arrow

    def test_a_small_pad_is_used_only_when_it_is_the_layouts_only_pad(self):
        """Industrial 1 (16 Nov 2026) has one Small pad, so every ship lands there; beside a Large pad a Small arrow is still not used."""
        self.tracker.pad_frames = {"industrial_2": {"pads": [{"size": "Small", "x": 100, "y": 100, "facing": 0}]}}
        self.land()
        self.assertIsNotNone(self.tracker.calibration)
        self.tracker._leave()
        self.tracker.pad_frames = {"industrial_2": {"pads": [{"size": "Small", "x": 100, "y": 100, "facing": 0}, {"size": "Small", "x": 500, "y": 100, "facing": 0}]}}
        self.land()
        self.assertIsNone(self.tracker.calibration)                      # two small pads and no number to tell them apart: not guessed

    def test_industrial_one_arrow_agrees_with_the_marked_walk(self):
        pad = settlement_track.known_pad_frames()["industrial_1"]["pads"][0]
        self.assertEqual(pad["size"], "Small")
        self.assertAlmostEqual(SettlementMaps().get("industrial_1")["scale"], 0.27)
        turn = (pad["facing"] - 260.0) % 360.0                           # ship heading 260 when landed; the marks fitted a turn of 98
        self.assertAlmostEqual(turn, 98.0, delta=2.0)

    def test_the_arrow_reading_agrees_with_the_real_shi_construction_frame(self):
        # Ben's Industrial 2 arrow (read from his picture) must turn the map within about 10 degrees of what real walks measured
        pad = settlement_track.known_pad_frames()["industrial_2"]["pads"][0]
        frame = settlement_track.known_frames()["industrial_2"]
        diff = (pad["facing"] - frame["offset"] + 180) % 360 - 180
        self.assertLess(abs(diff), 12, (pad, frame))

    def test_the_older_frame_still_wins_on_pad_one(self):
        self.tracker.frames = settlement_track.known_frames()
        self.land(pad=1)
        self.assertEqual(self.tracker.calibration.meta["how"], "dock")


class MarkedTerminalsCorrectTheLanding(LinedUpFromThePadArrow):
    """0.96.29: the landing line-up is rough, so terminals you MARK correct it (and a terminal the map lacks is not held against it)."""

    def test_marked_terminals_correct_a_rough_landing_line_up(self):
        from navigation import settlement_solve
        said = []
        self.tracker.say = said.append
        self.land(pad=1, heading=253.0)
        rough = self.tracker.calibration
        self.assertEqual(rough.meta["how"], "dock")
        # the truth: the map is turned 12 degrees more about the ship, and the ship sat 15 m away from where the arrow says
        ship = complex(*self.tracker.anchors["pad"])
        a = rough.a * cmath.exp(1j * math.radians(12))
        t = ship - a * ((ship - rough.t) / rough.a) + complex(9, 12)
        terminals = settlement_solve.features(self.maps.get("industrial_2"))["terminal"]
        pick = [p for p in terminals if p in ((1180.0, 28.0), (570.0, 315.0), (897.0, 577.0))]
        self.assertEqual(len(pick), 3)
        for x, y in pick:
            w = t + a * complex(x, -y)
            lat = self.tracker.settlement["lat"] + math.degrees(w.imag / RADIUS)
            lon = self.tracker.settlement["lon"] + math.degrees(w.real / (RADIUS * math.cos(math.radians(self.tracker.settlement["lat"]))))
            said.append(self.tracker.on_mark("terminal", here(lat, lon)))
        cal = self.tracker.calibration
        self.assertEqual(cal.meta["how"], "refined")
        self.assertFalse(self.tracker.provisional)
        for x, y in pick:
            w = t + a * complex(x, -y)
            mx, my = cal.from_world(w.real, w.imag)
            self.assertLess(math.hypot(mx - x, my - y), 12.0, (x, y))
        self.assertTrue(any("terminals you marked" in str(line) for line in said))

    def test_one_marked_terminal_changes_nothing(self):
        self.land(pad=1)
        self.tracker.on_mark("terminal", here(*TERMINALS[0][0]))
        self.assertEqual(self.tracker.calibration.meta["how"], "dock")
        self.assertTrue(self.tracker.provisional)


class RoughLandingLineUpsAreNotKept(MarkedTerminalsCorrectTheLanding):
    """0.96.33: Ben's ZIP of 15 Nov showed a remembered rough landing line-up (made with an older map size) being reused, so the corrections never came."""

    def test_a_rough_landing_line_up_survives_a_few_near_misses_but_not_a_far_one(self):
        self.land(pad=1)
        self.assertEqual(self.tracker.calibration.meta["how"], "dock")
        cal = self.tracker.calibration
        calls = []
        self.tracker._take_back = lambda: calls.append(1)
        original = settlement_track.settlement_solve.features
        try:
            settlement_track.settlement_solve.features = lambda data: {"stop": [(0.0, 0.0)]}
            for n in range(5):                                             # 5 stops about 100 map units from any terminal
                self.tracker._check_stop(*self.far_world(cal, 100.0))
            self.assertEqual(calls, [])
            self.tracker._check_stop(*self.far_world(cal, 300.0))          # one far miss: probably the wrong layout
            self.assertEqual(len(calls), 1)
        finally:
            settlement_track.settlement_solve.features = original

    @staticmethod
    def far_world(cal, units):
        w = cal.t + cal.a * complex(units, 0.0)                            # a place `units` map units from the map origin (the one fake terminal)
        return (w.real, w.imag)

    def test_a_remembered_landing_only_line_up_is_ignored(self):
        self.land(pad=1)
        rough = self.tracker.calibration.to_json()
        self.assertEqual(rough["how"], "dock")
        self.tracker.saved["4365483779"] = rough
        self.tracker._save()
        again = SettlementTracker(lambda: self.state, self.maps, MapView(), self.path)
        again.pad_frames, again.shipped, again.known = {}, {}, {}
        again.on_entry(dict(APPROACH))
        self.assertIsNone(again.calibration)

    def test_marks_still_correct_a_landing_line_up_two_stops_already_agreed_with(self):
        from navigation import settlement_solve
        self.land(pad=1, heading=253.0)
        self.tracker.provisional = False                                   # two stops had agreed with the rough line-up
        rough = self.tracker.calibration
        ship = complex(*self.tracker.anchors["pad"])
        a = rough.a * cmath.exp(1j * math.radians(10))
        t = ship - a * ((ship - rough.t) / rough.a)
        pick = [p for p in settlement_solve.features(self.maps.get("industrial_2"))["terminal"] if p in ((1180.0, 28.0), (570.0, 315.0), (897.0, 577.0))]
        for x, y in pick:
            w = t + a * complex(x, -y)
            lat = self.tracker.settlement["lat"] + math.degrees(w.imag / RADIUS)
            lon = self.tracker.settlement["lon"] + math.degrees(w.real / (RADIUS * math.cos(math.radians(self.tracker.settlement["lat"]))))
            self.tracker.on_mark("terminal", here(lat, lon))
        self.assertEqual(self.tracker.calibration.meta["how"], "refined")

    def test_a_corrected_line_up_is_remembered_and_dropped_when_the_map_picture_changes(self):
        from navigation import settlement_solve
        self.land(pad=1, heading=253.0)
        rough = self.tracker.calibration
        ship = complex(*self.tracker.anchors["pad"])
        a = rough.a * cmath.exp(1j * math.radians(8))
        t = ship - a * ((ship - rough.t) / rough.a)
        for x, y in ((1180.0, 28.0), (570.0, 315.0), (897.0, 577.0)):
            w = t + a * complex(x, -y)
            lat = self.tracker.settlement["lat"] + math.degrees(w.imag / RADIUS)
            lon = self.tracker.settlement["lon"] + math.degrees(w.real / (RADIUS * math.cos(math.radians(self.tracker.settlement["lat"]))))
            self.tracker.on_mark("terminal", here(lat, lon))
        self.assertEqual(self.tracker.calibration.meta["how"], "refined")
        same = SettlementTracker(lambda: self.state, self.maps, MapView(), self.path)
        same.pad_frames, same.shipped, same.known = {}, {}, {}
        same.on_entry(dict(APPROACH))
        self.assertIsNotNone(same.calibration)                              # the same picture: remembered
        data = self.maps.get("industrial_2")
        self.maps.maps["industrial_2"] = dict(data, ground=list(data.get("ground", [])) + [[[0, 0], [1, 1], [2, 2]]])      # a new picture
        changed = SettlementTracker(lambda: self.state, self.maps, MapView(), self.path)
        changed.pad_frames, changed.shipped, changed.known = {}, {}, {}
        changed.on_entry(dict(APPROACH))
        self.assertIsNone(changed.calibration)


class SameLayoutDifferentSettlements(Setup):
    def test_peng_and_makubuya_are_known_to_be_industrial_2(self):
        known = settlement_track.known_settlements()
        self.assertEqual(known.get("4367086339"), "industrial_2")      # Peng Synthetics Foundry
        self.assertEqual(known.get("4358173443"), "industrial_2")      # Makubuya Engineering Silo

    def test_the_real_visits_land_near_terminals_when_lined_up_from_the_landing(self):
        # real stops (metres east, north of the reference point) and the ship's heading on pad 1, 2026-11-11
        from navigation import settlement_solve
        feats = settlement_solve.features(self.maps.get("industrial_2"))["stop"]
        frame = settlement_track.known_frames()["industrial_2"]
        visits = [(181, [(-19, -128), (82, -24), (72, 36)]), (172, [(-19, -128), (80, -24), (72, 36)]), (74, [(130, 3), (10, 84), (-47, 64)])]
        for heading, stops in visits:
            cal = settlement_track.frame_calibration("industrial_2", frame, heading, 0, 0, 1e6)
            misses = [min(math.hypot(x - u, y - v) for u, v in feats) for x, y in (cal.from_world(e, n) for e, n in stops)]
            self.assertLess(sum(misses) / len(misses), settlement_track.DOCK_TRUST_UNITS, (heading, misses))


class AdoptLayout(Setup):
    """0.96.4: a finished base hack can tell the tracker which layout the base is, so the map comes up."""

    def test_taken_when_nothing_chosen(self):
        self.tracker.maps = SettlementMaps()               # several layouts share these pads, so none is chosen by itself
        self.tracker.on_entry(dict(APPROACH))
        self.tracker.on_entry(dict(DOCKING))
        self.assertIsNone(self.tracker.suggestion())
        self.assertTrue(self.tracker.adopt_layout("industrial_2", "4365483779"))
        self.assertEqual(self.tracker.suggestion(), "industrial_2")

    def test_not_taken_when_a_map_is_already_chosen_or_unknown_or_another_base(self):
        self.tracker.on_entry(dict(APPROACH))
        self.tracker.on_entry(dict(DOCKING))
        self.assertEqual(self.tracker.suggestion(), "industrial_2")
        self.assertFalse(self.tracker.adopt_layout("industrial_1", "4365483779"))
        self.tracker.settlement["map"] = None
        self.assertFalse(self.tracker.adopt_layout("no_such_map", "4365483779"))
        self.assertFalse(self.tracker.adopt_layout("industrial_2", "999"))
        self.assertFalse(self.tracker.adopt_layout(None))
        self.tracker.settlement = None
        self.assertFalse(self.tracker.adopt_layout("industrial_2"))

    def test_hint_from_an_earlier_hack_is_used_on_the_next_visit(self):
        self.tracker.maps = SettlementMaps()
        self.tracker.layout_hint = lambda market: "industrial_2" if market == "4365483779" else None
        self.tracker.on_entry(dict(APPROACH))
        self.assertEqual(self.tracker.suggestion(), "industrial_2")

    def test_a_failing_hint_never_breaks_arrival(self):
        def boom(market):
            raise RuntimeError("x")
        self.tracker.layout_hint = boom
        self.tracker.on_entry(dict(APPROACH))
        self.assertIsNotNone(self.tracker.settlement)


class AgricultureFourMeasured(unittest.TestCase):
    """Ben's three stops at Sharma Hydroponics Farm (15 Nov 2026), matched to the YELLOW (outside) terminals: the map's own size is 0.44 m per unit,
    not 0.325. (The first fit used a blue terminal and gave 0.37; the yellow ones agree with the pad's size on the picture.)"""
    A, B, C, PAD = (25.0, 25.0), (24.0, 141.5), (21.0, -255.0), (79.0, -162.0)           # metres east, north of the settlement's reference point

    def setUp(self):
        from navigation.settlement_maps import SettlementMaps
        self.data = SettlementMaps().get("agriculture_4")
        self.pad = next(p for p in settlement_track.known_pad_frames()["agriculture_4"]["pads"] if p["size"] == "Large")

    def calibration(self, heading=240.5):
        return settlement_track.pad_calibration("agriculture_4", self.pad, heading, self.PAD, 9.45, -94.41, 1104864.0, scale=self.pad["scale"])

    def test_the_map_carries_its_own_size(self):
        self.assertAlmostEqual(self.data["scale"], 0.44)
        self.assertAlmostEqual(self.pad["scale"], 0.44)

    def test_the_two_terminals_you_stood_at_land_on_the_two_yellow_map_terminals(self):
        cal = self.calibration()
        for stop, terminal in ((self.A, (845, 392)), (self.B, (962, 156))):
            x, y = cal.from_world(*stop)
            self.assertLess(math.hypot(x - terminal[0], y - terminal[1]), 25.0, stop)

    def test_the_old_shared_size_would_have_missed_the_far_one(self):
        old = settlement_track.pad_calibration("agriculture_4", self.pad, 240.5, self.PAD, 9.45, -94.41, 1104864.0)
        x, y = old.from_world(*self.B)
        self.assertGreater(math.hypot(x - 962, y - 156), 40.0)

    def test_the_solver_tries_a_measured_map_at_its_own_size(self):
        from navigation import settlement_solve
        scales, rng = settlement_solve.locked_for(self.data, settlement_solve.LOCKED_SCALES, settlement_solve.LOCKED_RANGE)
        self.assertEqual(scales, (0.44,))
        self.assertLess(rng[0], 0.44)
        self.assertGreater(rng[1], 0.44)
        other = settlement_solve.locked_for({"id": "x"}, settlement_solve.LOCKED_SCALES, settlement_solve.LOCKED_RANGE)
        self.assertEqual(other, (settlement_solve.LOCKED_SCALES, settlement_solve.LOCKED_RANGE))
        free = settlement_solve.locked_for(self.data, None, None)
        self.assertEqual(free, (None, None))              # the any-size pass is left alone

    def test_marked_terminals_correct_all_three_real_landings(self):
        spots = [("terminal", *self.C), ("terminal", *self.A), ("terminal", *self.B)]
        for ship, heading in (((79.0, -162.0), 240.5), ((60.0, -155.0), 239.0), ((79.0, -162.0), 242.0)):
            seed = settlement_track.pad_calibration("agriculture_4", self.pad, heading, ship, 9.45, -94.41, 1104864.0, scale=self.pad["scale"])
            cal, matched, missing = settlement_track.refine_calibration(seed, self.data, spots, ship)
            self.assertEqual((matched, missing), (3, 0))                      # C was a terminal the map lacked; it is on the map now (0.96.30)
            for stop, terminal in ((self.A, (845, 392)), (self.B, (962, 156))):
                x, y = cal.from_world(*stop)
                self.assertLess(math.hypot(x - terminal[0], y - terminal[1]), 8.0)
            cx, cy = cal.from_world(*self.C)
            self.assertLess(math.hypot(cx - 548, cy - 957), 12.0)             # the same place every time

    def test_not_enough_or_not_apart_means_no_correction(self):
        seed = settlement_track.pad_calibration("agriculture_4", self.pad, 240.5, self.PAD, 9.45, -94.41, 1104864.0, scale=self.pad["scale"])
        self.assertIsNone(settlement_track.refine_calibration(seed, self.data, [("terminal", *self.A)]))
        self.assertIsNone(settlement_track.refine_calibration(seed, self.data, [("terminal", 150.0, -300.0), ("terminal", *self.A)]))     # only one is on the map
        self.assertIsNone(settlement_track.refine_calibration(seed, self.data, [("terminal", 25.0, 25.0), ("terminal", 27.0, 30.0)]))   # too close together


class ShipMark(Setup):
    def test_mark_spot_ship_is_kept_and_not_used_to_solve(self):
        self.arrive()
        said = self.tracker.on_mark("ship", here(*SHIP))
        self.assertIn("Ship spot", said)
        self.assertIn("ship", self.tracker.anchors)
        self.assertEqual([k for k, _, _ in self.tracker.spots if k == "ship"], [])
        self.assertEqual(settlement_track.feature_of("my ship"), "ship")
        self.assertEqual(settlement_track.feature_of("landing pad"), "pad")


class AgricultureOneMeasured(unittest.TestCase):
    """Agnihotri Nutrition Holdings (15 Nov 2026): marked yellow terminals over two visits give 0.413 m per unit (first guess 0.435), close to
    Agriculture 4's 0.44 (the shared 0.325 made the landing line-up miss by 146 to 227 units and it was taken back)."""
    SHIP, MARKED, STOP = (45.0, -156.0), (4.0, 149.0), (137.0, 2.0)

    def setUp(self):
        from navigation.settlement_maps import SettlementMaps
        self.data = SettlementMaps().get("agriculture_1")
        self.pad = next(p for p in settlement_track.known_pad_frames()["agriculture_1"]["pads"] if p["size"] == "Large")

    def test_the_map_carries_its_size(self):
        self.assertAlmostEqual(self.data["scale"], 0.408)
        self.assertAlmostEqual(self.pad["scale"], 0.408)

    def test_two_terminals_correct_the_landing_line_up_to_the_yellow_ones(self):
        seed = settlement_track.pad_calibration("agriculture_1", self.pad, 221.0, self.SHIP, 9.0, -94.0, 1104864.0, scale=self.pad["scale"])
        cal, matched, missing = settlement_track.refine_calibration(seed, self.data, [("terminal", *self.MARKED), ("terminal", *self.STOP)], self.SHIP)
        self.assertEqual((matched, missing), (2, 0))
        for world, terminal in ((self.MARKED, (617, 644)), (self.STOP, (654, 189))):
            x, y = cal.from_world(*world)
            self.assertLess(math.hypot(x - terminal[0], y - terminal[1]), 25.0)
        ship_x, ship_y = cal.from_world(*self.SHIP)
        self.assertLess(math.hypot(ship_x - self.pad["x"], ship_y - self.pad["y"]), 130.0)      # the ship is on the Large pad


class YisWorkshopWideSearch(unittest.TestCase):
    """Yi's Workshop (16 Nov 2026): the landing line-up started about 200 degrees out, so only a search of every turn finds the three marked terminals.
    Two matching terminals fit the map two ways (turned half a circle apart); the right one puts the ship on the Large pad (940, 38)."""

    MARKS = [("terminal", 50.0, 59.1), ("terminal", 2.2, -2.5), ("terminal", -13.7, 38.5), ("terminal", 2.2, -2.5)]
    SHIP = (79.9, -45.8)

    def seed(self, data):
        pad = [p for p in settlement_track.known_pad_frames()["industrial_4"]["pads"] if p["size"] == "Large"][0]
        return settlement_track.pad_calibration("industrial_4", pad, 10.0, self.SHIP, 7.07, -90.0, 1100000.0, scale=0.34), pad

    def test_three_marks_correct_a_line_up_that_started_far_out(self):
        from navigation.settlement_maps import SettlementMaps
        data = SettlementMaps().get("industrial_4")
        seed, pad = self.seed(data)
        wide = settlement_track.refine_calibration(seed, data, self.MARKS, self.SHIP, turns=range(-180, 180), shift=None)
        self.assertEqual(wide[1], 3)
        self.assertAlmostEqual(abs(wide[0].a), 0.34, delta=0.02)
        self.assertAlmostEqual(wide[0].turn_degrees(), -78.0, delta=4.0)
        z = (complex(*self.SHIP) - wide[0].t) / wide[0].a                    # where the ship sits on the picture: on the Large pad, not near the small one
        self.assertLess(abs(complex(z.real, -z.imag) - complex(pad["x"], pad["y"])), 200.0)

    def test_industrial_4_carries_its_size_and_the_third_terminal_marked_four_times(self):
        from navigation.settlement_maps import SettlementMaps
        data = SettlementMaps().get("industrial_4")
        self.assertAlmostEqual(data["scale"], 0.34)
        marked = [m for m in data["markers"] if m.get("marked")]
        self.assertEqual([(m["x"], m["y"]) for m in marked], [(642, 330)])
