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

    def test_names_from_the_real_game(self):
        # taken from Benny's log, 8 Nov 2026
        self.assertTrue(subsystems.matches("engines", "$ext_drive_class2_a_name;", "Drive"))
        self.assertFalse(subsystems.matches("fsd", "$ext_drive_class2_a_name;", "Drive"))
        self.assertTrue(subsystems.matches("cargo", "$modularcargobaydoor_name;", "Cargo Hatch"))
        self.assertFalse(subsystems.matches("cargo", "$hpt_cargoscanner_size0_class5_name;", "Manifest Scanner"))
        self.assertTrue(subsystems.matches("weapons", "$hpt_beamlaser_gimbal_medium_name;", "Beam Laser"))
        self.assertTrue(subsystems.matches("powerplant", "$int_powerplant_size3_class3_name;", "Power Plant"))

    def test_phrases(self):
        r = test_macros.MacroTests().build()
        wanted = {"sub target the power plant": "sub_powerplant", "subtarget power plant": "sub_powerplant", "sub-target the engines": "sub_engines",
                  "target the shield generator": "sub_shields", "sub target the frame shift drive": "sub_fsd", "go for the life support": "sub_lifesupport",
                  "sub target the cargo hatch": "sub_cargo", "sub target the weapons": "sub_weapons", "sub target the drive": "sub_engines", "sub target the sensors": "sub_sensors", "lock the power distributor": "sub_distributor"}
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
        r.book.table["CyclePreviousSubsystem"] = (Keystroke("Key_P"), "")
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
            step = -1 if stroke.key == "Key_P" else 1
            position[0] = (position[0] + step) % (len(order) + 1)          # after the last part it wraps to "no subsystem"
            if drop_lock_at and len(presses) >= drop_lock_at:
                state.target_locked = False
            if position[0] < len(order):
                state.target_subsystem, state.target_subsystem_readable = order[position[0]]
            else:
                state.target_subsystem, state.target_subsystem_readable = "", ""
            state.target_seq += 1
            state.target_history.append((state.target_seq, state.target_subsystem, state.target_subsystem_readable))
            return None
        t.sender.send = send
        with self.assertLogs("starling", level="INFO"):
            outcome = r.run_text(phrase)[0]
        return outcome, presses

    def test_finds_the_power_plant(self):
        outcome, presses = self.run_command("sub target the power plant")
        self.assertEqual(outcome.status, "done")
        self.assertEqual(len(presses), 3)

    def test_a_part_written_twice_does_not_stop_the_search(self):
        # her 11:17 log: the game showed 'Drive' twice in a row, she took that for "all the way round" and gave up one press short
        order = [("$hpt_beamlaser_fixed_small_name;", "Beam Laser"), ("$ext_drive_class2_a_name;", "Drive"), ("$ext_drive_class2_a_name;", "Drive"),
                 ("$int_powerplant_size3_class3_name;", "Power Plant")]
        outcome, presses = self.run_command("sub target the power plant", order=order)
        self.assertEqual(outcome.status, "done")
        self.assertEqual(len(presses), 4)

    def test_goes_backwards_when_that_is_shorter(self):
        order = [("$ext_drive_class1_c_name;", "Drive"), ("$int_powerplant_size2_class3_name;", "Power Plant"), ("$int_hyperdrive_size3_class3_name;", "FSD"),
                 ("$int_lifesupport_size1_class3_name;", "Life Support"), ("$int_powerdistributor_size2_class3_name;", "Power Distributor"),
                 ("$int_shieldgenerator_size3_class5_name;", "Shield Generator"), ("$modularcargobaydoor_name;", "Cargo Hatch")]
        outcome, presses = self.run_command("sub target the power plant", order=order, start=4)      # from the distributor: 3 back, 6 forward
        self.assertEqual(outcome.status, "done")
        self.assertEqual(presses, ["Key_P"] * 3)

    def test_ring_choice(self):
        self.assertEqual(subsystems.shorter_way("distributor", "powerplant"), "previous")
        self.assertEqual(subsystems.shorter_way("powerplant", "distributor"), "next")
        self.assertEqual(subsystems.shorter_way(None, "powerplant"), "next")
        self.assertEqual(subsystems.shorter_way("weapons", "sensors"), "next")

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


class LeftPanelTabs(unittest.TestCase):
    def test_phrases_and_macros(self):
        from control.macros import actions_in, parse_macro
        r = test_macros.MacroTests().build()
        wanted = {"open contacts": ("panel_contacts", 2), "open the navigation tab": ("panel_navigation", 0),
                  "show transactions": ("panel_transactions", 1), "open the target tab": ("panel_target", 3), "contacts panel": ("panel_contacts", 2)}
        for text, (command_id, tab) in wanted.items():
            m = r.matcher.match(text)
            self.assertEqual(m.command.id, command_id, text)
            steps = parse_macro(m.command.macro)
            self.assertEqual(steps[0], ("openleft",))
            self.assertEqual(steps[1][:2], ("tab", tab))
            self.assertIn("FocusLeftPanel", actions_in(steps))
        self.assertEqual(r.matcher.match("open the left panel").command.id, "left_panel")


class FastLooking(unittest.TestCase):
    def test_monitor_looks_often_only_while_asked(self):
        import tempfile
        import time
        from pathlib import Path
        from journal.monitor import JournalMonitor

        class Counter:
            count = 0
            path = None
            processor = None

            def poll_once(self):
                self.count += 1
        with tempfile.TemporaryDirectory() as folder:
            monitor = JournalMonitor(Path(folder), None, None, poll_seconds=1.0)
            monitor.journal, monitor.status = Counter(), Counter()
            monitor.start()
            time.sleep(0.4)
            slow = monitor.journal.count
            monitor.look_fast(1.0)
            time.sleep(0.9)
            fast = monitor.journal.count - slow
            monitor.look_fast(0)
            time.sleep(0.3)
            monitor.stop()
        self.assertLessEqual(slow, 2)
        self.assertGreaterEqual(fast, 6)                      # about ten a second while fast

    def test_the_command_asks_for_fast_looking_and_always_hands_it_back(self):
        t = test_macros.MacroTests()
        r = t.build()
        asked = []
        r.journal_boost = asked.append
        from control.binds import Keystroke
        r.book.table = dict(r.book.table)
        r.book.table["CycleNextSubsystem"] = (Keystroke("Key_N"), "")
        state = GameState()                                    # nothing locked: she stops at once, but must still hand the boost back
        r.state_provider = lambda: state
        r.sleep = lambda s: None
        with self.assertLogs("starling", level="INFO"):
            r.run_text("sub target the power plant")
        self.assertEqual(asked, [40, 0])


class YesAndTheCommand(unittest.TestCase):
    def test_yes_followed_by_the_command_counts(self):
        from control.confirm import Confirmer

        class Match:
            phrase = "sub target shield generator"
        c = Confirmer(lambda: 0.0)
        c.ask(Match(), "target shield cell bank")
        self.assertEqual(c.answer("Yes, target the shield generator."), "yes")
        c.ask(Match(), "x")
        self.assertIsNone(c.answer("Yes, open the galaxy map"))          # a yes followed by something else is a new sentence
        c.ask(Match(), "x")
        self.assertEqual(c.answer("yes"), "yes")


class PressAhead(unittest.TestCase):
    """0.88.3: on a ship with many parts she presses ahead without waiting for each answer, then steps back over the extra presses.
    The fake game answers each key only after 0.55 s of fake time, like the real journal."""

    def run_lagged(self, phrase, order, lag=0.55, start=None, drop_every=0):
        t = test_macros.MacroTests()
        r = t.build()
        from control.binds import Keystroke
        r.book.table = dict(r.book.table)
        r.book.table["CycleNextSubsystem"] = (Keystroke("Key_N"), "")
        r.book.table["CyclePreviousSubsystem"] = (Keystroke("Key_P"), "")
        state = GameState()
        state.target_locked, state.target_scan = True, 3
        clock = [0.0]
        queue = []                                   # (arrives_at, step)
        position = [start if start is not None else -1]
        presses, seqs = [], [0]
        if start is not None:
            state.target_subsystem, state.target_subsystem_readable = order[start]

        def deliver():
            while queue and queue[0][0] <= clock[0]:
                _when, step = queue.pop(0)
                position[0] = (position[0] + step) % (len(order) + 1)
                if position[0] < len(order):
                    state.target_subsystem, state.target_subsystem_readable = order[position[0]]
                else:
                    state.target_subsystem, state.target_subsystem_readable = "", ""
                state.target_seq += 1
                state.target_history.append((state.target_seq, state.target_subsystem, state.target_subsystem_readable))

        def send(stroke, hold=0.0):
            presses.append(stroke.key)
            clock[0] += hold
            deliver()
            if drop_every and len(presses) % drop_every == 0:
                return None                           # the game lost this key press
            queue.append((clock[0] + lag, -1 if stroke.key == "Key_P" else 1))
            return None

        def sleep(seconds):
            clock[0] += seconds
            deliver()
        r.state_provider = lambda: state
        r.sleep = sleep
        t.sender.send = send
        with self.assertLogs("starling", level="INFO"):
            outcome = r.run_text(phrase)[0]
        deliver()
        return outcome, presses, clock[0], state

    def big_ship(self):
        weapons = [("$hpt_cannon_fixed_large_name;", "Cannon %d" % i) for i in range(1)]
        order = [("$modularcargobaydoor_name;", "Cargo Hatch")]
        for i in range(16):
            order.append(("$hpt_weapon%d_name;" % i, "Weapon %d" % i))
        order += [("$ext_drive_class7_a_name;", "Drive"), ("$int_powerplant_size6_class5_name;", "Power Plant"),
                  ("$int_hyperdrive_size5_class5_name;", "Frame Shift Drive"), ("$int_shieldgenerator_size6_class5_name;", "Shield Generator")]
        return order

    def test_finds_a_deep_part_faster_than_one_by_one(self):
        order = self.big_ship()
        outcome, presses, seconds, state = self.run_lagged("sub target the power plant", order)
        self.assertEqual(outcome.status, "done")
        self.assertIn("powerplant", [k for k in ("powerplant",) if subsystems.matches(k, state.target_subsystem, state.target_subsystem_readable)])
        one_by_one = 18 * 0.65                     # 18 presses at about 0.65 s each in the old way
        self.assertLess(seconds, one_by_one * 0.75)
        self.assertIn("Key_P", presses)            # it stepped back over the extra presses

    def test_ends_on_the_right_part_whatever_the_lag(self):
        order = self.big_ship()
        for lag in (0.2, 0.4, 0.55, 0.8, 1.1):
            outcome, _presses, _s, state = self.run_lagged("sub target the shield generator", order, lag=lag)
            self.assertEqual(outcome.status, "done", lag)
            self.assertTrue(subsystems.matches("shields", state.target_subsystem, state.target_subsystem_readable), lag)

    def test_a_lost_key_press_is_fixed_with_careful_steps(self):
        order = self.big_ship()
        outcome, _presses, _s, state = self.run_lagged("sub target the frame shift drive", order, drop_every=7)
        self.assertEqual(outcome.status, "done")
        self.assertTrue(subsystems.matches("fsd", state.target_subsystem, state.target_subsystem_readable))

    def test_a_missing_part_is_reported_not_endless(self):
        order = self.big_ship()
        outcome, presses, _s, _state = self.run_lagged("sub target the sensors", order)
        self.assertEqual(outcome.status, "no_subsystem")
        self.assertLess(len(presses), 45)

    def test_can_be_switched_off(self):
        t = test_macros.MacroTests()
        r = t.build()
        r.settings.set("subtarget.press_ahead", False)
        self.assertFalse(r.settings.get("subtarget.press_ahead", True))
