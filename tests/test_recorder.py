import json
import tempfile
import unittest
from pathlib import Path

from control.binds import BindingBook
from control.inputs import ButtonReader, JoyDevice, hat_directions
from control.recorder import (InputRecorder, describe_control, elite_control, format_report, save_recording,
                              suggest_macro)

X52 = JoyDevice(0, 0x06A3, 0x075C, "Saitek X52 Flight Control System", 32)

BINDS = """<?xml version="1.0" encoding="UTF-8" ?>
<Root>
  <UI_Select><Primary Device="06A3075C" Key="Joy_7" /><Secondary Device="Keyboard" Key="Key_Space" /></UI_Select>
  <UI_Up><Primary Device="06A3075C" Key="Joy_POV1Up" /><Secondary Device="Keyboard" Key="Key_UpArrow" /></UI_Up>
  <PrimaryFire><Primary Device="06A3075C" Key="Joy_7" /><Secondary Device="{NoDevice}" Key="" /></PrimaryFire>
  <GalaxyMapOpen><Primary Device="Keyboard" Key="Key_Grave" /><Secondary Device="{NoDevice}" Key="" /></GalaxyMapOpen>
  <OpenCodexGoToDiscovery><Primary Device="06A3075C" Key="Joy_9" /><Secondary Device="{NoDevice}" Key="" /></OpenCodexGoToDiscovery>
  <RequestDocking><Primary Device="06A3075C" Key="Joy_3"><Modifier Device="06A3075C" Key="Joy_5" /></Primary><Secondary Device="Keyboard" Key="Key_F6" /></RequestDocking>
  <Other><Primary Device="06A3075C" Key="Joy_3" /><Secondary Device="{NoDevice}" Key="" /></Other>
  <NamedStick><Primary Device="SaitekX52Pro" Key="Joy_11" /><Secondary Device="{NoDevice}" Key="" /></NamedStick>
</Root>
"""


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Script:
    """Pretend hardware: what is held at which time. holds = [(start, end, 'joy7' | 'hat:Up' | 'key:F6')]."""

    def __init__(self, clock, holds, start=100.0):
        self.clock, self.holds, self.start = clock, holds, start

    def _held(self):
        t = self.clock() - self.start
        return {name for a, b, name in self.holds if a <= t < b}

    # keyboard
    def all_down(self):
        from control.inputs import VK
        return [VK[n[4:]] for n in self._held() if n.startswith("key:")]

    def is_down(self, vk):
        return vk in self.all_down()

    # joystick
    def devices(self):
        return [X52]

    def buttons(self, index):
        return self.state(index)[0]

    def state(self, index):
        held = self._held()
        mask = 0
        for name in held:
            if name.startswith("joy"):
                mask |= 1 << (int(name[3:]) - 1)
        hat = 65535
        for name, value in (("hat:Up", 0), ("hat:Right", 9000), ("hat:Down", 18000), ("hat:Left", 27000)):
            if name in held:
                hat = value
        return mask, hat


def make(holds, status=None, journal=None):
    clock = Clock()
    script = Script(clock, holds)
    reader = ButtonReader(keyboard=script, joysticks=script, clock=clock)
    recorder = InputRecorder(reader, clock=clock, sleep=clock.sleep, status_reader=status, journal_factory=journal)
    return clock, recorder


class Helpers(unittest.TestCase):
    def test_hat_directions(self):
        self.assertEqual(hat_directions(0), {"Up"})
        self.assertEqual(hat_directions(9000), {"Right"})
        self.assertEqual(hat_directions(4500), {"Up", "Right"})
        self.assertEqual(hat_directions(31500), {"Up", "Left"})
        self.assertEqual(hat_directions(65535), set())
        self.assertEqual(hat_directions(None), set())

    def test_elite_names(self):
        self.assertEqual(elite_control("joy:06A3:075C:7"), ("06A3075C", "Joy_7"))
        self.assertEqual(elite_control("hat:06A3:075C:Up"), ("06A3075C", "Joy_POV1Up"))
        self.assertEqual(elite_control("key:Left"), ("Keyboard", "Key_LeftArrow"))
        self.assertEqual(elite_control("key:Numpad4"), ("Keyboard", "Key_Numpad_4"))
        self.assertEqual(elite_control("key:F6"), ("Keyboard", "Key_F6"))
        self.assertIsNone(elite_control("mouse:X1"))

    def test_describe(self):
        devices = [{"ident": "06A3:075C", "name": "Saitek X52 Flight Control System"}]
        self.assertEqual(describe_control("joy:06A3:075C:7", devices), "X52 button 7")
        self.assertEqual(describe_control("hat:06A3:075C:Up", devices), "X52 hat Up")
        self.assertEqual(describe_control("key:F6"), "keyboard F6")


class Recording(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        (Path(self.tmp.name) / "Custom.4.0.binds").write_text(BINDS, encoding="utf-8")
        self.book = BindingBook(self.tmp.name)

    def test_press_and_release_with_timing(self):
        clock, recorder = make([(0.5, 0.8, "joy7")])
        rec = recorder.record("t", 2.0)
        downs = [e for e in rec.events if e["type"] == "down"]
        ups = [e for e in rec.events if e["type"] == "up"]
        self.assertEqual(len(downs), 1)
        self.assertEqual(downs[0]["control"], "joy:06A3:075C:7")
        self.assertAlmostEqual(downs[0]["t"], 0.5, delta=0.03)
        self.assertAlmostEqual(ups[0]["held"], 0.3, delta=0.04)
        self.assertAlmostEqual(rec.seconds, 2.0, delta=0.03)

    def test_hat_and_keyboard_are_seen(self):
        _clock, recorder = make([(0.2, 0.4, "hat:Up"), (0.6, 0.7, "key:F6")])
        rec = recorder.record("t", 1.0)
        names = [e["control"] for e in rec.events if e["type"] == "down"]
        self.assertEqual(names, ["hat:06A3:075C:Up", "key:F6"])

    def test_button_still_held_at_the_end_is_closed(self):
        _clock, recorder = make([(0.5, 99, "joy1")])
        rec = recorder.record("t", 1.0)
        last = [e for e in rec.events if e["type"] == "up"][-1]
        self.assertTrue(last["cut_off"])
        self.assertAlmostEqual(last["held"], 0.5, delta=0.04)

    def test_stop_ends_early(self):
        clock, recorder = make([])
        rec = recorder.record("t", 10.0, stop=lambda: clock() - 100.0 > 0.3)
        self.assertLess(rec.seconds, 1.0)

    def test_game_context_is_recorded(self):
        clock = Clock()
        flags = {"GuiFocus": 0, "Flags": 0}

        def status():
            t = clock() - 100.0
            return {"GuiFocus": 6 if t > 0.5 else 0, "Flags": 1 if t > 1.0 else 0}
        sent = []

        class Journal:
            def __init__(self, sink):
                self.sink, self.done = sink, False

            def poll_once(self):
                if clock() - 100.0 > 0.8 and not self.done:
                    self.done = True
                    self.sink("DockingGranted")
        script = Script(clock, [(0.6, 0.7, "joy7")])
        reader = ButtonReader(keyboard=script, joysticks=script, clock=clock)
        recorder = InputRecorder(reader, clock=clock, sleep=clock.sleep, status_reader=status, journal_factory=Journal)
        rec = recorder.record("t", 2.0)
        kinds = [(e["type"], e.get("name")) for e in rec.events if e["type"] in ("screen", "switch", "journal")]
        self.assertIn(("screen", "galaxy map"), kinds)
        self.assertIn(("switch", "Docked"), kinds)
        self.assertIn(("journal", "DockingGranted"), kinds)
        down = [e for e in rec.events if e["type"] == "down"][0]
        self.assertEqual(down["screen"], 6)                      # pressed while the galaxy map was open

    def test_no_joystick_adds_a_note(self):
        clock = Clock()

        class Empty(Script):
            def devices(self):
                return []
        script = Empty(clock, [])
        recorder = InputRecorder(ButtonReader(keyboard=script, joysticks=script, clock=clock), clock=clock, sleep=clock.sleep)
        rec = recorder.record("t", 0.2)
        self.assertTrue(any("No joystick" in n for n in rec.notes))

    # ---- looking up actions ----
    def test_actions_are_found_and_menu_comes_first_on_a_screen(self):
        _c, recorder = make([(0.2, 0.3, "joy7")], status=lambda: {"GuiFocus": 6, "Flags": 0})
        rec = recorder.record("t", 1.0)
        report = format_report(rec, self.book)
        text = "\n".join(report)
        self.assertIn("X52 button 7", text)
        self.assertIn("-> UI_Select", text)
        self.assertIn("also: PrimaryFire", text)

    def test_ship_action_comes_first_with_no_screen_open(self):
        _c, recorder = make([(0.2, 0.3, "joy7")], status=lambda: {"GuiFocus": 0, "Flags": 0})
        text = "\n".join(format_report(recorder.record("t", 1.0), self.book))
        self.assertIn("-> PrimaryFire", text)

    def test_shift_button_picks_the_shifted_action(self):
        _c, recorder = make([(0.2, 0.9, "joy5"), (0.4, 0.5, "joy3")])
        rec = recorder.record("t", 1.5)
        steps, _notes = suggest_macro(rec, self.book)
        self.assertEqual(steps, ["RequestDocking"])               # the shift button itself is not a step

    def test_unshifted_press_does_not_get_the_shifted_action(self):
        _c, recorder = make([(0.4, 0.5, "joy3")])
        steps, _notes = suggest_macro(recorder.record("t", 1.0), self.book)
        self.assertEqual(steps, ["Other"])

    def test_device_named_differently_is_a_maybe(self):
        book = BindingBook(self.tmp.name)
        found = book.actions_for("06A3075C", "Joy_11")
        self.assertEqual([(m.action, m.sure) for m in found], [("NamedStick", False)])

    def test_joystick_names_listed(self):
        self.book.refresh()
        self.assertIn("SaitekX52Pro", self.book.joystick_names())
        self.assertNotIn("Keyboard", self.book.joystick_names())

    # ---- the macro suggestion ----
    def test_suggested_macro_waits_holds_and_repeats(self):
        holds = [(0.2, 0.25, "key:F6"),              # RequestDocking (keyboard secondary)
                 (1.7, 1.75, "hat:Up"),               # UI_Up after 1.45s
                 (2.0, 2.05, "hat:Up"),               # again quickly -> x2
                 (2.1, 2.15, "hat:Up"),               # and again -> x3
                 (3.0, 4.6, "joy7")]                  # held 1.6s
        _c, recorder = make(holds, status=lambda: {"GuiFocus": 6, "Flags": 0})
        steps, notes = suggest_macro(recorder.record("dock", 6.0), self.book)
        self.assertEqual(steps[0], "RequestDocking")
        self.assertIn("UI_Up x3", steps)
        self.assertTrue(steps[-1].startswith("hold UI_Select 1.6"), steps)
        wait = steps[steps.index("UI_Up x3") - 1]
        self.assertTrue(wait.startswith("wait 1.4") or wait.startswith("wait 1.5"), wait)
        self.assertEqual(notes, [])                  # everything here has a keyboard key

    def test_every_suggested_step_parses_as_a_macro(self):
        from control.macros import parse_macro
        holds = [(0.2, 0.25, "key:F6"), (1.0, 1.05, "hat:Up"), (2.0, 3.0, "joy7")]
        _c, recorder = make(holds, status=lambda: {"GuiFocus": 6, "Flags": 0})
        steps, _n = suggest_macro(recorder.record("x", 4.0), self.book)
        self.assertTrue(parse_macro(steps))

    def test_unknown_button_and_missing_keyboard_key_are_flagged(self):
        _c, recorder = make([(0.2, 0.3, "joy9"), (0.6, 0.7, "joy20")])
        steps, notes = suggest_macro(recorder.record("t", 1.0), self.book)
        self.assertEqual(steps, ["OpenCodexGoToDiscovery"])
        joined = " ".join(notes)
        self.assertIn("no keyboard key", joined)                  # joystick-only action
        self.assertIn("button 20 is not in your Elite controls file", joined)

    def test_short_gaps_are_dropped(self):
        _c, recorder = make([(0.2, 0.25, "key:F6"), (0.35, 0.4, "hat:Up")], status=lambda: {"GuiFocus": 6, "Flags": 0})
        steps, _n = suggest_macro(recorder.record("t", 1.0), self.book)
        self.assertEqual(steps, ["RequestDocking", "UI_Up"])

    def test_works_without_a_controls_file(self):
        empty = BindingBook(self.tmp.name + "/nothing")
        _c, recorder = make([(0.2, 0.3, "joy7")])
        text = "\n".join(format_report(recorder.record("t", 1.0), empty))
        self.assertIn("X52 button 7", text)
        self.assertIn("not found in your Elite controls file", text)

    def test_files_are_saved(self):
        _c, recorder = make([(0.2, 0.3, "joy7")])
        rec = recorder.record("Request docking!", 1.0)
        txt, raw = save_recording(rec, self.book, Path(self.tmp.name) / "recordings")
        self.assertTrue(txt.name.startswith("Request_docking_"))
        self.assertIn("SUGGESTED MACRO", txt.read_text(encoding="utf-8"))
        data = json.loads(raw.read_text(encoding="utf-8"))
        self.assertEqual(data["events"][0]["control"], "joy:06A3:075C:7")


NAMED_BINDS = """<?xml version="1.0" encoding="UTF-8" ?>
<Root>
  <FocusLeftPanel><Primary Device="SaitekX52" Key="Joy_POV1Left"><Modifier Device="SaitekX52" Key="Joy_6" /></Primary><Secondary Device="Keyboard" Key="Key_1" /></FocusLeftPanel>
  <UI_Select><Primary Device="SaitekX52" Key="Joy_4" /><Secondary Device="{NoDevice}" Key="" /></UI_Select>
  <FocusLeftPanel_Buggy><Primary Device="SaitekX52" Key="Joy_POV1Left"><Modifier Device="SaitekX52" Key="Joy_6" /></Primary><Secondary Device="{NoDevice}" Key="" /></FocusLeftPanel_Buggy>
  <CycleNextPanel><Primary Device="Keyboard" Key="Key_E" /><Secondary Device="SaitekX52" Key="Joy_17" /></CycleNextPanel>
  <CycleNextTarget><Primary Device="Keyboard" Key="Key_G" /><Secondary Device="SaitekX52" Key="Joy_17" /></CycleNextTarget>
  <UI_Back><Primary Device="SaitekX52" Key="Joy_3" /><Secondary Device="{NoDevice}" Key="" /></UI_Back>
  <CycleFireGroupNext><Primary Device="SaitekX52" Key="Joy_POV1Left" /><Secondary Device="{NoDevice}" Key="" /></CycleFireGroupNext>
</Root>
"""


class NamedStick(unittest.TestCase):
    """Elite writes some sticks by NAME (Device="SaitekX52"), not by USB id: found in a real recording."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        (Path(self.tmp.name) / "Custom.4.0.binds").write_text(NAMED_BINDS, encoding="utf-8")
        self.book = BindingBook(self.tmp.name)

    def test_ship_action_beats_srv_variant_and_menu_beats_target_cycling(self):
        from control.recorder import Recording
        rec = Recording("t", 3.0, devices=[{"ident": "06A3:075C", "name": "X52 H.O.T.A.S.", "buttons": 32, "x52": True}])
        rec.events = [
            {"t": 1.0, "type": "down", "control": "joy:06A3:075C:6", "with": [], "screen": 0},
            {"t": 1.3, "type": "down", "control": "hat:06A3:075C:Left", "with": ["joy:06A3:075C:6"], "screen": 0},
            {"t": 1.5, "type": "up", "control": "hat:06A3:075C:Left", "held": 0.2},
            {"t": 1.6, "type": "up", "control": "joy:06A3:075C:6", "held": 0.6},
            {"t": 2.8, "type": "down", "control": "joy:06A3:075C:17", "with": [], "screen": 2},
            {"t": 2.9, "type": "up", "control": "joy:06A3:075C:17", "held": 0.1},
        ]
        (Path(self.tmp.name) / "Custom.4.0.binds").write_text(
            NAMED_BINDS.replace('<FocusLeftPanel><Primary Device="SaitekX52" Key="Joy_POV1Left"><Modifier Device="SaitekX52" Key="Joy_6" /></Primary>',
                                '<FocusLeftPanel><Primary Device="Keyboard" Key="Key_1" />'), encoding="utf-8")
        steps, notes = suggest_macro(rec, BindingBook(self.tmp.name))
        self.assertEqual(steps[0], "FocusLeftPanel")
        self.assertEqual(steps[-1], "CycleNextPanel")
        self.assertTrue(any("ship action" in n for n in notes))

    def test_name_match_is_sure_and_shift_works(self):
        from control.recorder import Recording
        rec = Recording("t", 3.0, devices=[{"ident": "06A3:075C", "name": "X52 H.O.T.A.S.", "buttons": 32, "x52": True}])
        rec.events = [
            {"t": 1.0, "type": "down", "control": "joy:06A3:075C:6", "with": [], "screen": 0},
            {"t": 1.3, "type": "down", "control": "hat:06A3:075C:Left", "with": ["joy:06A3:075C:6"], "screen": 0},
            {"t": 1.5, "type": "up", "control": "hat:06A3:075C:Left", "held": 0.2},
            {"t": 1.6, "type": "up", "control": "joy:06A3:075C:6", "held": 0.6},
            {"t": 2.0, "type": "down", "control": "joy:06A3:075C:4", "with": [], "screen": 2},
            {"t": 2.1, "type": "up", "control": "joy:06A3:075C:4", "held": 0.1},
        ]
        steps, notes = suggest_macro(rec, self.book)
        self.assertEqual(steps, ["FocusLeftPanel", "wait 0.65", "UI_Select"])
        text = "\n".join(format_report(rec, self.book))
        self.assertNotIn("(?)", text)
        raw = save_recording(rec, self.book, Path(self.tmp.name) / "r")[1]
        resolved = json.loads(raw.read_text(encoding="utf-8"))["resolved"]
        self.assertEqual(resolved[1]["actions"][0], "FocusLeftPanel")
        self.assertTrue(resolved[0]["shift_only"])


class ConsoleTool(unittest.TestCase):
    def test_full_run_with_fakes(self):
        from control.record_buttons import run_record_buttons

        class Settings:
            def get(self, key, default=None):
                return {"recorder.seconds": 3, "recorder.countdown": 1}.get(key, default)

        class App:
            settings = Settings()
            reader = None

            def ensure_buttons(self):
                return self.reader
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        (Path(tmp.name) / "Custom.4.0.binds").write_text(BINDS, encoding="utf-8")
        clock = Clock()
        script = Script(clock, [(1.5, 1.6, "joy7")])
        app = App()
        app.reader = ButtonReader(keyboard=script, joysticks=script, clock=clock)
        answers = iter(["request docking", ""])
        lines = []
        # the countdown sleeps one second per step, so the script starts after it: shift it
        script.start = 101.0
        code = run_record_buttons(app, out=lines.append, ask=lambda _p: next(answers), sleep=clock.sleep,
                                  beep=lambda _h: None, flush=lambda: None, folder=Path(tmp.name) / "rec",
                                  book=BindingBook(tmp.name), clock=clock)
        self.assertEqual(code, 0)
        text = "\n".join(lines)
        self.assertIn("1 button presses were recorded", text)
        self.assertTrue(list((Path(tmp.name) / "rec").glob("request_docking_*.txt")))

    def test_no_reader(self):
        from control.record_buttons import run_record_buttons

        class App:
            def ensure_buttons(self):
                return None
        lines = []
        self.assertEqual(run_record_buttons(App(), out=lines.append), 1)


if __name__ == "__main__":
    unittest.main()
