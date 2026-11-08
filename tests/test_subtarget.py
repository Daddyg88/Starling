"""Sub targeting: "sub target the power plant" (0.86.0)."""
import unittest

from control import subsystems
from journal.game_state import GameState
from tests import test_macros

ORDER = [("$int_engine_size5_class5_name;", "Thrusters"), ("$int_hyperdrive_size5_class5_name;", "Frame Shift Drive"),
         ("$int_powerplant_size6_class5_name;", "Power Plant"), ("$int_shieldgenerator_size6_class5_name;", "Shield Generator")]


class Matching(unittest.TestCase):
    def test_names(self):
        self.assertTrue(subsystems.matches("powerplant", "$int_powerplant_size6_class5_name;", ""))
        self.assertTrue(subsystems.matches("powerplant", "", "Power Plant"))
        self.assertTrue(subsystems.matches("engines", "$int_engine_size5;", ""))
        self.assertTrue(subsystems.matches("fsd", "$int_hyperdrive_size5;", "Frame Shift Drive"))
        self.assertFalse(subsystems.matches("engines", "$int_hyperdrive_size5;", "Frame Shift Drive"))     # "drive" must not mean the FSD
        self.assertFalse(subsystems.matches("powerplant", "", ""))

    def test_phrases(self):
        r = test_macros.MacroTests().build()
        wanted = {"sub target the power plant": "sub_powerplant", "subtarget power plant": "sub_powerplant", "sub-target the engines": "sub_engines",
                  "target the shield generator": "sub_shields", "sub target the frame shift drive": "sub_fsd", "go for the life support": "sub_lifesupport",
                  "sub target the cargo hatch": "sub_cargo", "sub target the sensors": "sub_sensors", "lock the power distributor": "sub_distributor"}
        for text, command_id in wanted.items():
            m = r.matcher.match(text)
            self.assertIsNotNone(m, text)
            self.assertEqual(m.command.id, command_id, text)


class Commands(unittest.TestCase):
    def run_command(self, phrase, order=ORDER, start=None, locked=True, scan=3, silent=False, drop_lock_at=None):
        t = test_macros.MacroTests()
        r = t.build()
        from control.binds import Keystroke
        r.book.table = dict(r.book.table)                       # a copy: the table is shared by other tests
        r.book.table["CycleNextSubsystem"] = (Keystroke("Key_N"), "")
        state = GameState()
        state.target_locked, state.target_scan = locked, scan
        position = [start if start is not None else -1]
        presses = []
        if start is not None:
            state.target_subsystem, state.target_subsystem_readable = order[start]
        r.state_provider = lambda: state
        r.sleep = lambda s: None

        def send(stroke, hold=0.0):
            t.sender.pressed.append(stroke)
            presses.append(stroke.key)
            if silent:
                return None
            position[0] = (position[0] + 1) % (len(order) + 1)             # after the last part it wraps to "no subsystem"
            if drop_lock_at and len(presses) >= drop_lock_at:
                state.target_locked = False
            if position[0] < len(order):
                state.target_subsystem, state.target_subsystem_readable = order[position[0]]
            else:
                state.target_subsystem, state.target_subsystem_readable = "", ""
            state.target_seq += 1
            return None
        t.sender.send = send
        with self.assertLogs("starling", level="INFO"):
            outcome = r.run_text(phrase)[0]
        return outcome, presses

    def test_finds_the_power_plant(self):
        outcome, presses = self.run_command("sub target the power plant")
        self.assertEqual(outcome.status, "done")
        self.assertEqual(len(presses), 3)

    def test_already_selected_presses_nothing(self):
        outcome, presses = self.run_command("sub target the power plant", start=2)
        self.assertEqual((outcome.status, presses), ("done", []))

    def test_wraps_round_a_missing_part_then_gives_up(self):
        outcome, presses = self.run_command("sub target the sensors")
        self.assertEqual(outcome.status, "no_subsystem")
        self.assertLessEqual(len(presses), 8)

    def test_nothing_locked(self):
        outcome, presses = self.run_command("sub target the power plant", locked=False)
        self.assertEqual((outcome.status, presses), ("no_target", []))

    def test_not_scanned(self):
        outcome, presses = self.run_command("sub target the engines", scan=1)
        self.assertEqual((outcome.status, presses), ("no_scan", []))

    def test_journal_silent_stops_after_one_press(self):
        outcome, presses = self.run_command("sub target the power plant", silent=True)
        self.assertEqual(outcome.status, "sub_unread")
        self.assertEqual(len(presses), 1)

    def test_target_lost_midway(self):
        outcome, presses = self.run_command("sub target the shield generator", drop_lock_at=2)
        self.assertEqual(outcome.status, "no_target")
        self.assertEqual(len(presses), 2)

    def test_every_status_has_a_voice_pool(self):
        import json
        from pathlib import Path
        from control.runner import LINE_FOR_STATUS
        pools = json.loads(Path("voicepacks/default/commands.json").read_text(encoding="utf-8"))
        for status in ("no_target", "no_scan", "no_subsystem", "sub_unread"):
            self.assertIn(LINE_FOR_STATUS[status], pools)


class JournalToState(unittest.TestCase):
    def test_target_event_fills_the_state(self):
        from events import combat_events
        cls = [c for c in combat_events.EVENT_CLASSES if c.__name__.endswith("ShipTargeted") or getattr(c, "name", "") == "ShipTargeted"]
        self.assertTrue(cls)
        state = GameState()
        entry = {"event": "ShipTargeted", "TargetLocked": True, "ScanStage": 3, "Ship": "viper_mkiii", "Subsystem": "$int_powerplant_size6_class5_name;",
                 "Subsystem_Localised": "Power Plant"}
        combat_events._target_update(type("X", (), {"_seen": None, "_bounty_told": None, "_pending": ""})(), entry, state)
        self.assertEqual((state.target_scan, state.target_seq), (3, 1))
        self.assertTrue(subsystems.matches("powerplant", state.target_subsystem, state.target_subsystem_readable))
        combat_events._target_update(type("X", (), {"_seen": None, "_bounty_told": None, "_pending": ""})(),
                                     {"event": "ShipTargeted", "TargetLocked": False}, state)
        self.assertEqual(state.target_subsystem, "")
        self.assertFalse(state.target_locked)


if __name__ == "__main__":
    unittest.main()
