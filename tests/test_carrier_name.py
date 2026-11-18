import unittest
from types import SimpleNamespace

from events.carriers import CarrierStats, is_own_carrier, looks_like_callsign, spoken_station
from events.docked import Docked
from journal.game_state import GameState
from tests.test_habits import Env


class Names(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        CarrierStats().update_state({"Callsign": "K7Q-B0Z", "Name": "Ben's Rest", "CarrierID": 3700000001}, self.state)

    def test_callsign_shape(self):
        self.assertTrue(looks_like_callsign("K7Q-B0Z"))
        self.assertFalse(looks_like_callsign("Jameson Memorial"))

    def test_own_carrier_by_callsign_name_or_market_id(self):
        self.assertTrue(is_own_carrier({"StationName": "K7Q-B0Z"}, self.state))
        self.assertTrue(is_own_carrier({"StationName": "ben's rest"}, self.state))
        self.assertTrue(is_own_carrier({"StationName": "X", "MarketID": 3700000001, "StationType": "FleetCarrier"}, self.state))
        self.assertFalse(is_own_carrier({"StationName": "Q1A-C2D", "StationType": "FleetCarrier"}, self.state))

    def test_she_says_the_name_not_the_serial(self):
        entry = {"StationName": "K7Q-B0Z", "StationType": "FleetCarrier", "StarSystem": "Sol"}
        Docked().update_state(entry, self.state)
        self.assertEqual(self.state.station, "Ben's Rest")
        self.assertEqual(self.state.fleet_carrier_system, "Sol")

    def test_other_carrier_name_when_known_else_serial(self):
        entry = {"StationName": "Q1A-C2D", "StationType": "FleetCarrier"}
        self.assertEqual(spoken_station(entry, self.state), "Q1A-C2D")
        self.state.carrier_names["Q1A-C2D"] = "Lucky Star"
        self.assertEqual(spoken_station(entry, self.state), "Lucky Star")

    def test_ordinary_station_untouched(self):
        self.assertEqual(spoken_station({"StationName": "Jameson Memorial", "StationType": "Coriolis"}, self.state), "Jameson Memorial")


class Counting(Env):
    def test_own_carrier_visits_are_never_called_out(self):
        self.keeper = self.make(own_carrier=lambda d: d.get("StationName") == "K7Q-B0Z")
        for _ in range(8):
            self.dock("K7Q-B0Z")
        self.assertEqual(self.said, [])
        self.assertNotIn("K7Q-B0Z", self.keeper.stations)

    def test_other_station_still_counts(self):
        self.keeper = self.make(own_carrier=lambda d: False)
        for _ in range(3):
            self.dock()
        self.assertEqual(self.keys(), ["Habit_Station_Week"])

    def test_carrier_name_used_for_other_carriers(self):
        self.keeper = self.make(station_name=lambda d: "Lucky Star")
        for _ in range(3):
            self.dock("Q1A-C2D")
        self.assertEqual(self.said[0][1]["station"], "Lucky Star")


if __name__ == "__main__":
    unittest.main()
