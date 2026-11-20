"""'How far is my carrier?': she remembers your carrier between sessions and says its NAME, never the serial."""

import json
import tempfile
import unittest
from pathlib import Path

from events import carriers
from events.registry import load_registry
from journal.game_state import GameState
from tests import test_neutron


class Spansh(test_neutron.FakeSpansh):
    def coordinates(self, name):
        self.asked.append(("coords", name))
        return {"Colonia": (-9530.0, -910.0, 19808.0)}.get(name)


class AskTests(unittest.TestCase):
    build = test_neutron.VoiceTests.build
    keys = test_neutron.VoiceTests.keys

    def setUp(self):
        self.build(spansh=Spansh())
        self.state.fleet_carrier_name = "Sea Breeze"
        self.state.fleet_carrier_callsign = "K7Q-B0Z"
        self.state.star_pos = (0.0, 0.0, 0.0)

    def test_distance_from_the_position_the_journal_gave(self):
        self.state.fleet_carrier_system = "Colonia"
        self.state.fleet_carrier_pos = (3.0, 4.0, 0.0)
        for text in ("how far is my carrier", "how far away is my fleet carrier", "how far am I from my carrier",
                     "what's the distance to my carrier", "where is my carrier", "which system is my carrier in", "how far is the carrier away"):
            self.narr.said.clear()
            self.assertIsNotNone(self.v.try_handle(text), text)
            self.assertEqual(self.keys(), ["CarrierWhere"], text)
            fields = self.narr.said[0][1]
            self.assertEqual((fields["carrier"], fields["system"], fields["distance"]), ("Sea Breeze", "Colonia", "5.0"), text)
            self.assertNotIn("K7Q", fields["carrier"])

    def test_distance_is_looked_up_when_the_journal_gave_no_position(self):
        self.state.fleet_carrier_system = "Colonia"
        self.v.try_handle("how far is my carrier")
        self.assertIn(("coords", "Colonia"), self.spansh.asked)
        self.assertEqual(self.keys(), ["CarrierWhere"])
        self.assertTrue(self.narr.said[0][1]["ly"] > 20000)

    def test_unknown_distance_still_names_the_system(self):
        self.state.fleet_carrier_system = "Nowhere"
        self.v.try_handle("how far is my carrier")
        self.assertEqual(self.keys(), ["CarrierWhereNoDistance"])

    def test_same_system(self):
        self.state.fleet_carrier_system = "Sol"
        self.v.try_handle("where is my carrier")
        self.assertEqual(self.keys(), ["CarrierWhereHere"])

    def test_unknown_carrier(self):
        self.v.try_handle("how far is my carrier")
        self.assertEqual(self.keys(), ["CarrierFleetUnknown"])

    def test_squad_carrier_uses_its_bookmark(self):
        self.build(spansh=Spansh(), bookmarks__squad="Colonia")
        self.state.star_pos = (0.0, 0.0, 0.0)
        self.v.try_handle("how far is the squad carrier")
        self.assertEqual(self.narr.said[0][1]["carrier"], "squad carrier")

    def test_plotting_uses_the_name_too(self):
        self.state.fleet_carrier_system = "Colonia"
        self.v.try_handle("take us to my carrier")
        self.assertEqual(self.narr.said[0][1]["carrier"], "Sea Breeze")

    def test_route_questions_are_not_stolen(self):
        self.state.fleet_carrier_system = "Colonia"
        self.v.try_handle("plot a route to my carrier")
        self.assertEqual(self.keys()[0], "CarrierPlotting")


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "carrier.json"
        carriers.MEMORY_FILE = self.path
        carriers._last_saved.clear()
        self.addCleanup(setattr, carriers, "MEMORY_FILE", None)

    def feed(self, state, entry):
        event = load_registry()[entry["event"]]
        event.update_state(entry, state)

    def test_remembered_after_a_restart(self):
        first = GameState()
        self.feed(first, {"event": "CarrierStats", "Callsign": "K7Q-B0Z", "Name": "Sea Breeze", "CarrierID": 3700000000})
        self.feed(first, {"event": "CarrierJump", "StarSystem": "Colonia", "StationName": "K7Q-B0Z", "StarPos": [1, 2, 3]})
        self.assertEqual(json.loads(self.path.read_text())["fleet_carrier_name"], "Sea Breeze")
        second = GameState()
        carriers.load_memory(second)
        self.assertEqual((second.fleet_carrier_name, second.fleet_carrier_system, second.fleet_carrier_pos), ("Sea Breeze", "Colonia", (1.0, 2.0, 3.0)))

    def test_the_journal_wins_over_memory(self):
        self.path.write_text(json.dumps({"fleet_carrier_system": "Old", "fleet_carrier_name": "Old Name"}))
        state = GameState()
        state.fleet_carrier_name = "New Name"
        carriers.load_memory(state)
        self.assertEqual((state.fleet_carrier_name, state.fleet_carrier_system), ("New Name", "Old"))

    def test_a_broken_file_is_ignored(self):
        self.path.write_text("{nope")
        carriers.load_memory(GameState())

    def test_a_new_system_clears_the_old_position(self):
        state = GameState()
        state.fleet_carrier_callsign = "K7Q-B0Z"
        state.fleet_carrier_system, state.fleet_carrier_pos = "Sol", (1.0, 1.0, 1.0)
        self.feed(state, {"event": "CarrierLocation", "StarSystem": "Colonia"})
        self.assertIsNone(state.fleet_carrier_pos)


class LineTests(unittest.TestCase):
    def test_lines_exist(self):
        data = json.loads(Path("voicepacks/default/carriers.json").read_text(encoding="utf-8"))
        for key in ("CarrierWhere", "CarrierWhereNoDistance", "CarrierWhereHere"):
            self.assertGreaterEqual(len(data[key]), 2, key)


if __name__ == "__main__":
    unittest.main()
