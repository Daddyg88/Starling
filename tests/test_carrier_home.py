"""Your own carrier is home: its name (never its serial) in every docking line, no landing count, and 'where is home' finds it."""

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from core.ships import ship_name
from memory.habits import HabitKeeper
from tests import test_neutron
from tests.helpers import make_processor


class DockingLineTests(unittest.TestCase):
    def setUp(self):
        self.processor, _bus, self.heard = make_processor()
        state = self.processor.state
        state.fleet_carrier_callsign, state.fleet_carrier_name = "J7T-8XL", "HMS Gadsden"

    def names(self, event):
        return [e.data.get("StationName") for e in self.heard if e.name == event]

    def test_docking_granted_says_the_name_not_the_serial(self):
        self.processor.handle_entry({"event": "DockingGranted", "StationName": "J7T-8XL", "LandingPad": 16})
        self.assertEqual(self.names("DockingGranted"), ["HMS Gadsden"])

    def test_requested_and_undocked_too(self):
        self.processor.handle_entry({"event": "DockingRequested", "StationName": "J7T-8XL"})
        self.processor.handle_entry({"event": "Undocked", "StationName": "J7T-8XL"})
        self.assertEqual(self.names("DockingRequested"), ["HMS Gadsden"])
        self.assertEqual(self.names("Undocked"), ["HMS Gadsden"])

    def test_someone_elses_carrier_keeps_its_serial(self):
        self.processor.handle_entry({"event": "DockingGranted", "StationName": "K7Q-B0Z", "LandingPad": 3})
        self.assertEqual(self.names("DockingGranted"), ["K7Q-B0Z"])

    def test_an_ordinary_station_is_untouched(self):
        self.processor.handle_entry({"event": "DockingGranted", "StationName": "Jameson Memorial", "LandingPad": 3})
        self.assertEqual(self.names("DockingGranted"), ["Jameson Memorial"])


class HabitTests(unittest.TestCase):
    def make(self, homes):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        return HabitKeeper(None, Path(self.dir.name) / "habits.json", announce=lambda key, values: None, now=lambda: datetime(2026, 11, 20, 12, 0),
                           home_names=lambda: homes)

    def test_old_counts_for_the_carrier_are_thrown_away(self):
        keeper = self.make(("J7T-8XL", "HMS Gadsden"))
        keeper.stations = {"J7T-8XL": {"count": 26, "recent": [], "last": "2026-11-19"}, "Jameson Memorial": {"count": 9, "recent": [], "last": "2026-11-19"}}
        self.assertEqual(keeper.favourite_station(), ("Jameson Memorial", 9))
        self.assertEqual(keeper.top_stations(), [("Jameson Memorial", 9)])
        self.assertNotIn("J7T-8XL", keeper.stations)

    def test_home_alone_means_no_favourite(self):
        keeper = self.make(("J7T-8XL",))
        keeper.stations = {"j7t-8xl": {"count": 30, "recent": [], "last": "2026-11-19"}}
        self.assertIsNone(keeper.favourite_station())

    def test_without_a_known_carrier_nothing_changes(self):
        keeper = self.make(())
        keeper.stations = {"J7T-8XL": {"count": 26, "recent": [], "last": "2026-11-19"}}
        self.assertEqual(keeper.favourite_station(), ("J7T-8XL", 26))


class AskTests(unittest.TestCase):
    build = test_neutron.VoiceTests.build
    keys = test_neutron.VoiceTests.keys

    def setUp(self):
        self.build()
        self.state.fleet_carrier_name = "HMS Gadsden"
        self.state.fleet_carrier_callsign = "J7T-8XL"
        self.state.fleet_carrier_system = "Kharahua"
        self.state.system = "Kharahua"

    def test_the_questions_from_the_log(self):
        for text in ("what s our fleet carrier", "what is our fleet carrier", "do you know the name of our fleet carrier", "what is my carrier called",
                     "where is home", "how far is home", "where is our fleet carrier"):
            self.narr.said.clear()
            self.assertIsNotNone(self.v.try_handle(text), text)
            self.assertEqual(self.keys(), ["CarrierWhereHere"], text)
            self.assertEqual(self.narr.said[0][1]["carrier"], "HMS Gadsden")

    def test_home_is_left_alone_when_no_carrier_is_known(self):
        self.state.fleet_carrier_system = None
        self.assertIsNone(self.v.try_handle("where is home"))


class SuitNameTests(unittest.TestCase):
    def test_the_game_code_never_gets_spoken(self):
        self.assertEqual(ship_name("", "$UtilitySuit_Class1_Name;"), "Artemis suit")
        self.assertEqual(ship_name("$ExplorationSuit_Class2_Name;"), "Maverick suit")
        self.assertEqual(ship_name("Federal Corvette", "Federal Corvette"), "Federal Corvette")
        self.assertNotIn("$", ship_name("", "$Whatever_Name;"))


if __name__ == "__main__":
    unittest.main()
