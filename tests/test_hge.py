import json
import tempfile
import unittest
from pathlib import Path

from core.event_bus import EventBus
from events.registry import load_registry
from journal.game_state import GameState
from journal.processor import EventProcessor


class Hge(unittest.TestCase):
    def run_lines(self, entries):
        bus, got = EventBus(), []
        bus.subscribe("*", lambda e: got.append(e.name))
        state = GameState()
        state.system = "Test"
        proc = EventProcessor(bus, {}, state, load_registry())
        for e in entries:
            proc.handle_entry(e)
        return got

    def test_high_grade_is_called_out_once_instead_of_signal_detected(self):
        hge = {"event": "FSSSignalDiscovered", "SystemAddress": 1, "SignalName": "$USS_HighGradeEmissions;",
               "SignalName_Localised": "Unidentified signal source", "USSType": "$USS_Type_X;", "USSType_Localised": "High Grade Emissions"}
        got = self.run_lines([hge, hge])
        self.assertEqual(got.count("HighGradeEmissions"), 1)
        self.assertNotIn("FSSSignalDiscovered", got)

    def test_other_signals_stay_normal(self):
        other = {"event": "FSSSignalDiscovered", "SystemAddress": 1, "SignalName": "$USS_Type_Salvage;", "USSType": "$USS_Type_Salvage;"}
        got = self.run_lines([other])
        self.assertEqual(got, ["FSSSignalDiscovered"])

    def test_new_system_calls_out_again(self):
        a = {"event": "FSSSignalDiscovered", "SystemAddress": 1, "SignalName": "$USS_HighGradeEmissions;"}
        b = dict(a, SystemAddress=2)
        self.assertEqual(self.run_lines([a, b]).count("HighGradeEmissions"), 2)

    def test_lines_exist(self):
        data = json.loads(Path("voicepacks/default/callouts.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(data["HighGradeEmissions"]), 5)


if __name__ == "__main__":
    unittest.main()
