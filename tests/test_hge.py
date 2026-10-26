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


class Hint(unittest.TestCase):
    def entry(self, allegiance, *states, boss="Fac"):
        return {"SystemFaction": {"Name": boss}, "Factions": [{"Name": boss, "Allegiance": allegiance,
                "FactionState": states[0] if states else "None", "ActiveStates": [{"State": s} for s in states]}]}

    def test_boom_and_expansion_give_the_proto_group(self):
        from journal.hge_states import likely_materials, spoken_list
        for state in ("Boom", "Expansion"):
            label, mats = likely_materials(self.entry("Independent", state))
            self.assertEqual(label, state)
            self.assertEqual(spoken_list(mats), "Proto Heat Radiators, Proto Light Alloys and Proto Radiolic Alloys")
        self.assertEqual(likely_materials(self.entry("Alliance", "Boom"))[1][0], "Proto Heat Radiators")

    def test_other_rows(self):
        from journal.hge_states import likely_materials
        self.assertEqual(likely_materials(self.entry("Empire", "None"))[1], ["Imperial Shielding"])
        self.assertEqual(likely_materials(self.entry("Federation", "Election"))[1][0], "Core Dynamics Composites")
        self.assertEqual(likely_materials(self.entry("Independent", "Civil War"))[1][0], "Military Grade Alloys")
        self.assertEqual(likely_materials(self.entry("Empire", "Outbreak"))[1], ["Pharmaceutical Isolators"])
        self.assertIsNone(likely_materials(self.entry("Independent", "Bust")))
        self.assertIsNone(likely_materials({"event": "FSDJump"}))

    def test_arrival_announces_hint_and_switch_silences_it(self):
        got = {}
        bus = EventBus()
        bus.subscribe("*", lambda e: got.setdefault(e.name, e.data))
        state = GameState()
        proc = EventProcessor(bus, {}, state, load_registry())
        entry = dict(self.entry("Independent", "Boom"), event="FSDJump", StarSystem="Thor", StarPos=[0, 0, 0])
        proc.handle_entry(entry)
        self.assertIn("HighGradeHint", got)
        self.assertIn("Proto Light Alloys", got["HighGradeHint"]["Materials"])
        from personality import categories
        from types import SimpleNamespace
        off = SimpleNamespace(get=lambda k, d=None: False if k == "exploration.hge_hint" else d)
        self.assertFalse(categories.allowed(SimpleNamespace(name="HighGradeHint", priority="low", data={}), off))
