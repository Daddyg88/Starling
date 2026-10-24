"""Routes to the fleet carrier and the squad carrier."""

import json
import unittest

from events.registry import load_registry
from journal.game_state import GameState
from navigation.voice import slot_key, slot_name
from tests import test_neutron


class CarrierVoice(unittest.TestCase):
    build = test_neutron.VoiceTests.build
    keys = test_neutron.VoiceTests.keys

    def test_phrases_find_the_carriers(self):
        self.assertEqual(slot_key("my fleet carrier"), "fleet")
        self.assertEqual(slot_key("the carrier"), "fleet")
        self.assertEqual(slot_key("the squad carrier"), "squad")
        self.assertEqual(slot_key("our squadron carrier"), "squad")
        self.assertEqual(slot_key("home"), "home")
        self.assertEqual(slot_key("bookmark three"), "b3")
        self.assertEqual(slot_name("squad"), "Squad carrier")

    def test_route_to_my_fleet_carrier_from_the_journal(self):
        for text in ("plot a route to my fleet carrier", "plot a neutron route to my carrier", "take us to my carrier",
                     "set a course for my fleet carrier", "navigate to the carrier", "Starling, plot me a route to my carrier please"):
            self.build()
            self.state.fleet_carrier_system = "Colonia"
            self.assertIsNotNone(self.v.try_handle(text), text)
            self.assertIn(("find", "Colonia"), self.spansh.asked, text)
            self.assertEqual(self.keys()[0], "CarrierPlotting", text)

    def test_fleet_carrier_falls_back_to_the_bookmark(self):
        self.build(bookmarks__fleet="Colonia")
        self.v.try_handle("plot a route to my fleet carrier")
        self.assertIn(("find", "Colonia"), self.spansh.asked)

    def test_squad_carrier_uses_its_bookmark(self):
        self.build(bookmarks__squad="Colonia")
        for text in ("plot a route to the squad carrier", "take us to the squadron carrier"):
            self.build(bookmarks__squad="Colonia")
            self.v.try_handle(text)
            self.assertIn(("find", "Colonia"), self.spansh.asked, text)

    def test_squad_carrier_is_not_the_fleet_carrier(self):
        self.build(bookmarks__squad="Colonia")
        self.state.fleet_carrier_system = "Sol"
        self.v.try_handle("plot a route to the squad carrier")
        self.assertIn(("find", "Colonia"), self.spansh.asked)
        self.assertNotIn(("find", "Sol"), self.spansh.asked)

    def test_nothing_known_is_explained(self):
        self.build(system="Alpha")
        self.v.try_handle("plot a route to my carrier")
        self.assertEqual(self.keys(), ["CarrierFleetUnknown"])
        self.build(system="Alpha")
        self.v.try_handle("plot a route to the squad carrier")
        self.assertEqual(self.keys(), ["CarrierNoSquad"])
        self.build(system="Alpha")
        self.state.squadron = "The Lancers"
        self.v.try_handle("plot a route to the squad carrier")
        self.assertEqual(self.keys(), ["CarrierSquadUnknown"])
        self.assertEqual(self.narr.said[0][1]["squadron"], "The Lancers")
        self.assertEqual(self.spansh.asked, [])

    def test_already_there(self):
        self.build(system="Colonia")
        self.state.fleet_carrier_system = "colonia"
        self.v.try_handle("plot a route to my carrier")
        self.assertEqual(self.keys(), ["CarrierHere"])
        self.assertEqual(self.spansh.asked, [])

    def test_save_by_voice(self):
        self.build(system="Colonia")
        self.settings.save = lambda: None            # never write the shared test settings file
        self.v.try_handle("save this system as the squad carrier")
        self.assertEqual(self.settings.get("bookmarks.squad"), "Colonia")
        self.v.try_handle("save this system as my carrier")
        self.assertEqual(self.settings.get("bookmarks.fleet"), "Colonia")

    def test_ordinary_routes_still_work(self):
        self.build()
        self.v.try_handle("plot a neutron route to colonia")
        self.assertIn(("find", "Colonia"), self.spansh.asked)
        self.assertEqual(self.keys()[0], "RoutePlotting")


class CarrierJournal(unittest.TestCase):
    def feed(self, *entries):
        registry, state = load_registry(), GameState()
        for entry in entries:
            registry[entry["event"]].update_state(entry, state)
        return state

    def test_events_are_registered_and_quiet(self):
        registry = load_registry()
        for name in ("CarrierStats", "CarrierLocation", "CarrierJump", "SquadronStartup"):
            self.assertIn(name, registry)
            self.assertFalse(registry[name].announce)

    def test_carrier_location_sets_the_system(self):
        state = self.feed({"event": "CarrierLocation", "CarrierID": 1, "StarSystem": "Colonia"})
        self.assertEqual(state.fleet_carrier_system, "Colonia")

    def test_only_my_carrier_jump_counts(self):
        mine = [{"event": "CarrierStats", "Callsign": "K7Q-B0Z"}]
        state = self.feed(*mine, {"event": "CarrierJump", "StationName": "K7Q-B0Z", "StarSystem": "Sol"})
        self.assertEqual(state.fleet_carrier_system, "Sol")
        state = self.feed(*mine, {"event": "CarrierJump", "StationName": "ZZZ-999", "StarSystem": "Sol"})
        self.assertIsNone(state.fleet_carrier_system)

    def test_docking_at_my_carrier_updates_it(self):
        state = self.feed({"event": "CarrierStats", "Callsign": "K7Q-B0Z"},
                          {"event": "Docked", "StationName": "k7q-b0z", "StationType": "FleetCarrier", "StarSystem": "Achenar"})
        self.assertEqual(state.fleet_carrier_system, "Achenar")
        state = self.feed({"event": "Location", "StationName": "OTHER", "StarSystem": "Sol", "Docked": True})
        self.assertIsNone(state.fleet_carrier_system)

    def test_squadron(self):
        self.assertEqual(self.feed({"event": "SquadronStartup", "SquadronName": "The Lancers"}).squadron, "The Lancers")


class CarrierLines(unittest.TestCase):
    def test_lines_exist_and_are_clean(self):
        from pathlib import Path
        data = json.loads(Path("voicepacks/default/carriers.json").read_text(encoding="utf-8"))
        banned = ("laugh", "giggle", "chortle", "uploading", "baka", "ug,", "uhh", "gtfo")
        for key in ("CarrierPlotting", "CarrierHere", "CarrierFleetUnknown", "CarrierSquadUnknown", "CarrierNoSquad"):
            self.assertGreaterEqual(len(data[key]), 3, key)
        for key, lines in data.items():
            if key.startswith("_"):
                continue
            self.assertEqual(len(lines), len(set(lines)), key)
            for line in lines:
                self.assertFalse([b for b in banned if b in line.lower()], line)


class DropOut(unittest.TestCase):
    def test_exit_supercruise_phrases(self):
        from control.catalog import CATALOG
        from control.matcher import Matcher
        m = Matcher(CATALOG)
        for text in ("exit supercruise", "drop out", "drop us out", "safe disengage", "leave super cruise"):
            hit = m.match(text)
            self.assertEqual(hit.command.id, "exit_supercruise", text)
            self.assertEqual(hit.command.action, "Supercruise")
        self.assertEqual(m.match("engage supercruise").command.id, "supercruise")
