import json
import os
import tempfile
import unittest
from pathlib import Path

from journal.status_reader import FLAG_IN_DANGER, FLAG_LOW_FUEL, StatusReader
from tests.helpers import make_processor


class StatusReaderTests(unittest.TestCase):
    def setUp(self):
        self.processor, _bus, self.heard = make_processor()
        self.reader = StatusReader(None, self.processor, min_gap_seconds={})

    def test_low_fuel_is_announced_once_when_it_switches_on(self):
        self.reader.handle_status({"Flags": 0})
        self.reader.handle_status({"Flags": FLAG_LOW_FUEL, "Fuel": {"FuelMain": 6.0}})
        self.reader.handle_status({"Flags": FLAG_LOW_FUEL, "Fuel": {"FuelMain": 5.9}})
        self.assertEqual([e.name for e in self.heard], ["LowFuel"])
        self.assertEqual(self.heard[0].priority, "critical")

    def test_low_fuel_can_be_announced_again_after_recovering(self):
        for flags in (0, FLAG_LOW_FUEL, 0, FLAG_LOW_FUEL):
            self.reader.handle_status({"Flags": flags})
        self.assertEqual(len(self.heard), 2)

    def test_percentage_uses_fuel_tank_size_when_known(self):
        self.processor.state.fuel_capacity = 32.0
        self.reader.handle_status({"Flags": FLAG_LOW_FUEL, "Fuel": {"FuelMain": 8.0}})
        self.assertEqual(self.heard[0].data["fuel_percent"], 25)

    def test_flicker_is_limited_by_minimum_gap(self):
        reader = StatusReader(None, self.processor, min_gap_seconds={"InDanger": 3600})
        for flags in (FLAG_IN_DANGER, 0, FLAG_IN_DANGER):
            reader.handle_status({"Flags": flags})
        self.assertEqual(len(self.heard), 1)

    def test_baseline_mode_stays_quiet(self):
        self.reader.handle_status({"Flags": FLAG_LOW_FUEL}, baseline_only=True)
        self.assertEqual(self.heard, [])


class StatusFileTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.dir = Path(self.folder.name)
        self.processor, _bus, self.heard = make_processor()

    def tearDown(self):
        self.folder.cleanup()

    def test_fresh_file_with_low_fuel_is_announced_at_start(self):
        (self.dir / "Status.json").write_text(json.dumps({"Flags": FLAG_LOW_FUEL, "Fuel": {"FuelMain": 3.0}}))
        StatusReader(self.dir, self.processor, min_gap_seconds={}).poll_once()
        self.assertEqual([e.name for e in self.heard], ["LowFuel"])

    def test_old_file_from_last_session_is_not_announced(self):
        path = self.dir / "Status.json"
        path.write_text(json.dumps({"Flags": FLAG_LOW_FUEL}))
        os.utime(path, (1000, 1000))
        StatusReader(self.dir, self.processor, min_gap_seconds={}).poll_once()
        self.assertEqual(self.heard, [])

    def test_half_written_file_is_not_a_crash(self):
        (self.dir / "Status.json").write_text('{"Flags": 12')
        StatusReader(self.dir, self.processor).poll_once()
        self.assertEqual(self.heard, [])

    def test_missing_file_is_not_a_crash(self):
        StatusReader(self.dir, self.processor).poll_once()
        self.assertEqual(self.heard, [])


if __name__ == "__main__":
    unittest.main()


SHIP = 1 << 24      # "in the main ship"
SRV = 1 << 26
GEAR, HARDPOINTS, SUPERCRUISE, SCOOP, CHARGING, FSDJUMP = 1 << 2, 1 << 6, 1 << 4, 1 << 11, 1 << 17, 1 << 30


class ControlsAndScreensTests(unittest.TestCase):
    def setUp(self):
        self.processor, _bus, self.heard = make_processor()
        self.reader = StatusReader(None, self.processor, min_gap_seconds={})
        self.now = [100.0]
        self.reader._clock = lambda: self.now[0]

    def names(self):
        return [e.name for e in self.heard]

    def test_landing_gear_down_and_up(self):
        self.reader.handle_status({"Flags": SHIP})
        self.reader.handle_status({"Flags": SHIP | GEAR})
        self.reader.handle_status({"Flags": SHIP})
        self.assertEqual(self.names(), ["LandingGearDown", "LandingGearUp"])

    def test_hardpoints_night_vision_and_lights(self):
        self.reader.handle_status({"Flags": SHIP})
        self.reader.handle_status({"Flags": SHIP | HARDPOINTS | (1 << 28) | (1 << 8)})
        self.assertEqual(sorted(self.names()), ["HardpointsDeployed", "LightsOn", "NightVisionOn"])

    def test_galaxy_map_opens_and_closes(self):
        self.reader.handle_status({"Flags": SHIP, "GuiFocus": 0})
        self.reader.handle_status({"Flags": SHIP, "GuiFocus": 6})
        self.reader.handle_status({"Flags": SHIP, "GuiFocus": 0})
        self.assertEqual(self.names(), ["GalaxyMapOpened", "ScreenClosed"])
        self.assertEqual(self.heard[1].data["screen"], "galaxy map")

    def test_vehicle_change_is_announced(self):
        self.reader.handle_status({"Flags": SHIP})
        self.reader.handle_status({"Flags": SRV})
        self.assertEqual(self.names(), ["VehicleChanged"])
        self.assertEqual(self.heard[0].data["vehicle"], "SRV")

    def test_on_foot_warnings_are_critical(self):
        self.reader.handle_status({"Flags": 0, "Flags2": 1})
        self.reader.handle_status({"Flags": 0, "Flags2": 1 | (1 << 6)})
        self.assertEqual(self.names(), ["LowOxygen"])
        self.assertEqual(self.heard[0].priority, "critical")

    def test_start_up_does_not_narrate_the_cockpit(self):
        # lights, gear and night vision are already on when STARLING starts...
        self.reader.handle_status({"Flags": SHIP | GEAR | (1 << 8) | (1 << 28) | (1 << 19)}, initial=True)
        # ...so only the safety warning is announced
        self.assertEqual(self.names(), ["LowFuel"])

    def test_gear_does_not_repeat_while_it_stays_down(self):
        for _ in range(3):
            self.reader.handle_status({"Flags": SHIP | GEAR})
        self.assertEqual(self.names(), ["LandingGearDown"])

    # ---- the problems found while playing ----
    def test_gear_flag_is_ignored_after_switching_to_the_srv(self):
        self.reader.handle_status({"Flags": SHIP})
        self.reader.handle_status({"Flags": SRV | GEAR})      # the game rewrites flags on the switch
        self.reader.handle_status({"Flags": SRV | GEAR})
        self.assertEqual(self.names(), ["VehicleChanged"])

    def test_nothing_is_announced_for_a_vehicle_that_is_not_the_main_ship(self):
        self.reader.handle_status({"Flags": SHIP})
        self.reader.handle_status({"Flags": GEAR | HARDPOINTS})   # no ship bit: e.g. the Nomad
        self.reader.handle_status({"Flags": GEAR})
        self.assertEqual(self.names(), ["VehicleChanged"])
        self.assertEqual(self.heard[0].data["vehicle"], "other vehicle")

    def test_going_on_foot_does_not_announce_landing_gear(self):
        self.reader.handle_status({"Flags": SHIP})
        self.reader.handle_status({"Flags": GEAR, "Flags2": 1})
        self.assertEqual(self.names(), ["VehicleChanged"])
        self.assertEqual(self.heard[0].data["vehicle"], "on foot")

    def test_boarding_the_ship_again_is_one_event_not_a_storm(self):
        self.reader.handle_status({"Flags": 0, "Flags2": 1})
        self.reader.handle_status({"Flags": SHIP | GEAR | (1 << 8)})
        self.assertEqual(self.names(), ["VehicleChanged"])
        self.assertEqual(self.heard[0].data["vehicle"], "main ship")

    def test_hardpoints_are_ignored_in_supercruise(self):
        self.reader.handle_status({"Flags": SHIP | SUPERCRUISE})
        self.reader.handle_status({"Flags": SHIP | SUPERCRUISE | HARDPOINTS})
        self.reader.handle_status({"Flags": SHIP | SUPERCRUISE})
        self.assertEqual(self.names(), [])

    def test_hardpoints_are_ignored_during_the_jump_itself(self):
        self.reader.handle_status({"Flags": SHIP})
        self.reader.handle_status({"Flags": SHIP | FSDJUMP | HARDPOINTS})
        self.assertEqual(self.names(), [])

    def test_hardpoints_left_out_after_supercruise_are_not_announced_late(self):
        self.reader.handle_status({"Flags": SHIP | SUPERCRUISE | HARDPOINTS})
        self.reader.handle_status({"Flags": SHIP | HARDPOINTS})   # dropped out, still on
        self.assertEqual(self.names(), [])

    def test_hardpoints_flipped_during_supercruise_are_not_announced_when_you_drop_out(self):
        self.reader.handle_status({"Flags": SHIP | HARDPOINTS}, initial=True)
        self.reader.handle_status({"Flags": SHIP | SUPERCRUISE | HARDPOINTS})
        self.reader.handle_status({"Flags": SHIP | SUPERCRUISE})      # game retracts them in supercruise
        self.reader.handle_status({"Flags": SHIP})                    # dropped out
        self.assertEqual(self.names(), [])
        self.reader.handle_status({"Flags": SHIP | HARDPOINTS})       # you deploy them for real
        self.assertEqual(self.names(), ["HardpointsDeployed"])

    def test_hardpoints_in_normal_space_are_announced(self):
        self.reader.handle_status({"Flags": SHIP})
        self.reader.handle_status({"Flags": SHIP | HARDPOINTS})
        self.reader.handle_status({"Flags": SHIP})
        self.assertEqual(self.names(), ["HardpointsDeployed", "HardpointsRetracted"])

    # ---- fuel scooping: started / complete (tank full) / disengaged (you leave) ----
    def scoop(self, on=True, fuel=None):
        status = {"Flags": SHIP | (SCOOP if on else 0)}
        if fuel is not None:
            status["Fuel"] = {"FuelMain": fuel}
        self.reader.handle_status(status)

    def test_scooping_to_a_full_tank_then_leaving(self):
        self.processor.state.fuel_capacity = 32.0
        self.scoop(False, 20.0)
        self.scoop(True, 20.0)          # fuel starts flowing
        self.now[0] += 4
        self.scoop(True, 28.0)
        self.scoop(True, 32.0)          # tank is full
        self.scoop(True, 32.0)          # still in range: no repeat
        self.now[0] += 4
        self.scoop(False, 32.0)         # you leave
        self.assertEqual(self.names(), ["FuelScoopStarted", "FuelScoopComplete", "FuelScoopDisengaged"])

    def test_leaving_early_says_disengaged_but_not_complete(self):
        self.processor.state.fuel_capacity = 32.0
        self.scoop(False, 10.0)
        self.scoop(True, 12.0)
        self.now[0] += 8
        self.scoop(False, 15.0)
        self.assertEqual([n for n in self.names() if n != "FuelHalf"], ["FuelScoopStarted", "FuelScoopDisengaged"])

    def test_tank_filling_in_the_same_moment_the_scoop_stops_says_complete_first(self):
        self.processor.state.fuel_capacity = 32.0
        self.scoop(False, 20.0)
        self.scoop(True, 20.0)
        self.now[0] += 6
        self.scoop(False, 32.0)
        self.assertEqual(self.names(), ["FuelScoopStarted", "FuelScoopComplete", "FuelScoopDisengaged"])

    def test_nearly_full_counts_as_full(self):
        self.processor.state.fuel_capacity = 32.0
        self.scoop(False, 20.0)
        self.scoop(True, 31.95)
        self.assertIn("FuelScoopComplete", self.names())

    def test_second_scoop_gets_its_own_calls(self):
        self.processor.state.fuel_capacity = 32.0
        for _ in range(2):
            self.scoop(False, 10.0)
            self.scoop(True, 12.0)
            self.scoop(True, 32.0)
            self.now[0] += 6
            self.scoop(False, 32.0)
        self.assertEqual(self.names().count("FuelScoopComplete"), 2)
        self.assertEqual(self.names().count("FuelScoopDisengaged"), 2)

    def test_unknown_tank_size_never_claims_full(self):
        self.scoop(False, 10.0)
        self.scoop(True, 40.0)
        self.assertNotIn("FuelScoopComplete", self.names())

    def test_a_flicker_of_the_scoop_is_not_called_disengaged(self):
        self.processor.state.fuel_capacity = 32.0
        self.scoop(False, 10.0)
        self.scoop(True, 11.0)
        self.now[0] += 1
        self.scoop(False, 11.0)
        self.assertEqual([n for n in self.names() if n != "FuelHalf"], ["FuelScoopStarted"])

    def test_no_tank_full_call_while_in_the_srv_or_on_foot(self):
        self.processor.state.fuel_capacity = 32.0
        self.reader.handle_status({"Flags": SRV | SCOOP, "Fuel": {"FuelMain": 32.0}})
        self.assertNotIn("FuelScoopComplete", self.names())

    def test_frame_shift_drive_charging_is_announced(self):
        self.reader.handle_status({"Flags": SHIP})
        self.reader.handle_status({"Flags": SHIP | CHARGING})
        self.assertEqual(self.names(), ["FsdCharging"])

    def test_menu_readings_are_quiet_and_the_return_is_a_fresh_start(self):
        self.reader.handle_status({"Flags": 0})
        self.reader.handle_status({"Flags": SHIP | GEAR | (1 << 8)})
        self.assertEqual(self.names(), [])

    def test_low_fuel_is_still_announced_on_a_fresh_start(self):
        self.reader.handle_status({"Flags": 0})
        self.reader.handle_status({"Flags": SHIP | (1 << 19)})
        self.assertEqual(self.names(), ["LowFuel"])


class NomadTests(unittest.TestCase):
    """Uses the real Flags numbers from a debug session with the Nomad."""

    SHIP_MASS_LOCKED = 153157640       # in the main ship, mass locked
    NOMAD_LAUNCHED = 203423816         # game says InSRV (+ hardpoints, analysis mode)
    NOMAD_GEAR_DOWN = 203423820
    NOMAD_LANDED = 203423822
    ON_FOOT_FLAGS, ON_FOOT_FLAGS2 = 2097152, 33041
    BACK_IN_SHIP = 153157704

    def setUp(self):
        self.processor, _bus, self.heard = make_processor()
        self.reader = StatusReader(None, self.processor, min_gap_seconds={})

    def names(self):
        return [e.name for e in self.heard]

    def play_the_session(self):
        r = self.reader
        r.handle_status({"Flags": self.SHIP_MASS_LOCKED}, initial=True)
        self.processor.handle_line('{"event":"LaunchVessel","VesselType":"lander01","VesselType_Localised":"Nomad"}', silent=True)
        r.handle_status({"Flags": self.NOMAD_LAUNCHED})
        r.handle_status({"Flags": self.NOMAD_GEAR_DOWN})
        r.handle_status({"Flags": self.NOMAD_LANDED})
        r.handle_status({"Flags": self.ON_FOOT_FLAGS, "Flags2": self.ON_FOOT_FLAGS2})   # steps out
        r.handle_status({"Flags": self.NOMAD_LANDED})                                    # gets back in
        r.handle_status({"Flags": self.NOMAD_GEAR_DOWN})                                 # lifts off (Landed goes off)
        r.handle_status({"Flags": self.BACK_IN_SHIP})

    def test_launch_vessel_marks_the_nomad(self):
        self.processor.handle_line('{"event":"LaunchVessel","VesselType":"lander01","VesselType_Localised":"Nomad"}', silent=True)
        self.assertTrue(self.processor.state.in_nomad)

    def test_launching_a_normal_srv_clears_it(self):
        self.processor.state.in_nomad = True
        self.processor.handle_line('{"event":"LaunchSRV","SRVType":"testbuggy"}', silent=True)
        self.assertFalse(self.processor.state.in_nomad)

    def test_the_whole_nomad_session_is_calm(self):
        self.play_the_session()
        # only one landing gear call-out, and no weapons/gear/analysis-mode storms
        self.assertEqual(self.names().count("LandingGearDown"), 1)
        for noisy in ("HardpointsDeployed", "HardpointsRetracted", "AnalysisModeOn", "CombatModeOn",
                      "LandingGearUp", "MassLocked", "MassLockReleased", "ColdWarning"):
            self.assertNotIn(noisy, self.names())

    def test_vehicle_changes_in_the_session(self):
        self.play_the_session()
        vehicles = [e.data["vehicle"] for e in self.heard if e.name == "VehicleChanged"]
        self.assertEqual(vehicles, ["Nomad", "on foot", "Nomad", "main ship"])

    def test_boarding_the_main_ship_afterwards_clears_the_nomad(self):
        self.play_the_session()
        self.assertFalse(self.processor.state.in_nomad)
