"""Macro tests: request docking, deploy Nomad, and the flicker-free Home page."""

import tempfile
import unittest
from pathlib import Path

from control.binds import Keystroke
from control.macros import actions_in, parse_macro
from control.runner import CommandRunner
from core.event_bus import EventBus
from journal.game_state import GameState
from tests.test_commands import FakeBook, FakeSender, FakeSpeech
from tests.test_phase6b import dialogue, make_settings

ALL = {name: (Keystroke("Key_%s" % i), "") for i, name in enumerate(
    ["FocusLeftPanel", "FocusRightPanel", "FocusRadarPanel", "CycleNextPanel", "UI_Select", "UI_Right", "UI_Back", "UI_Down", "CyclePreviousPanel"])}


class MacroTests(unittest.TestCase):
    def build(self, table=None, **values):
        self.sender, self.speech = FakeSender(), FakeSpeech()
        self.sleeps = []
        return CommandRunner(EventBus(), self.speech, dialogue(), make_settings(**values),
                             book=FakeBook(ALL if table is None else table), sender=self.sender,
                             state_provider=lambda: GameState(), sleep=self.sleeps.append)

    def test_parse(self):
        self.assertEqual(parse_macro(["FocusLeftPanel", "UI_Down x3", "wait 0.5"]),
                         [("press", "FocusLeftPanel", 1), ("press", "UI_Down", 3), ("wait", 0.5)])
        self.assertEqual(actions_in(parse_macro(["A", "B x2", "A"])), ["A", "B"])
        with self.assertRaises(ValueError):
            parse_macro(["press the big red button"])

    def test_many_ways_to_ask_for_docking(self):
        r = self.build()
        for text in ("request docking", "requesting docking", "ask for docking permission", "request permission to dock",
                     "can I dock", "send a docking request", "contact the station for docking clearance"):
            m = r.matcher.match(text)
            self.assertIsNotNone(m, text)
            self.assertEqual(m.command.id, "request_docking", text)

    def test_many_ways_to_ask_for_the_nomad(self):
        r = self.build()
        for text in ("deploy nomad", "deploy the nomad", "launch the nomad", "send out the nomad", "launch my nomad"):
            m = r.matcher.match(text)
            self.assertIsNotNone(m, text)
            self.assertEqual(m.command.id, "deploy_nomad", text)

    def test_docking_runs_the_commanders_sequence(self):
        r = self.build()
        r.run_text("request docking")
        names = [s.key for s in self.sender.pressed]
        # 0.34.4: focus left panel, Next Tab x2, Right, Select, Previous Tab x2, Back
        self.assertEqual(names, ["Key_0", "Key_3", "Key_3", "Key_5", "Key_4", "Key_8", "Key_8", "Key_6"])
        self.assertNotIn("Key_7", names)
        self.assertIn(1.2, self.sleeps)

    def test_your_own_steps_replace_the_built_in_ones(self):
        r = self.build(macros__deploy_nomad=["FocusRightPanel", "wait 1", "UI_Down x2", "UI_Select"])
        r.run_text("deploy the nomad")
        self.assertEqual([s.key for s in self.sender.pressed], ["Key_1", "Key_7", "Key_7", "Key_4"])

    def test_the_nomad_looks_down_then_presses_down_right_then_select(self):
        r = self.build()
        r.run_text("deploy the nomad")
        self.assertEqual([s.key for s in self.sender.pressed], ["Key_2", "Key_7", "Key_5", "Key_4"])

    def test_a_missing_key_stops_before_pressing_anything(self):
        table = {k: v for k, v in ALL.items() if k != "CycleNextPanel"}
        r = self.build(table)
        r.run_text("request docking")
        self.assertEqual(self.sender.pressed, [])

    def test_a_broken_macro_in_settings_is_explained_not_run(self):
        r = self.build(macros__deploy_nomad=["do something clever"])
        out = r.execute(r.matcher.match("deploy the nomad"))
        self.assertEqual(out.status, "failed")
        self.assertIn("settings", out.detail)
        self.assertEqual(self.sender.pressed, [])

    def test_a_failed_press_stops_the_macro(self):
        r = self.build()
        self.sender.fail_on = None
        original = self.sender.send
        calls = []

        def send(stroke, hold=None):
            calls.append(stroke)
            return "game_not_active" if len(calls) == 2 else original(stroke)
        self.sender.send = send
        r.run_text("request docking")
        self.assertEqual(len(calls), 2)

    def test_the_key_check_and_explain_know_about_macros(self):
        r = self.build()
        self.assertIn("macro", r.explain("request docking")[0])
        table = {k: v for k, v in ALL.items() if k != "UI_Select"}
        r2 = self.build(table)
        _working, problems = r2.binding_report()
        self.assertTrue(any("docking" in label or "UI_Select" in why for label, why in problems) or problems)


class FlickerTests(unittest.TestCase):
    def test_home_rows_are_updated_in_place(self):
        from unittest.mock import MagicMock
        from ui.dashboard import Dashboard

        class Label:
            created = 0

            def __init__(self, *a, **k):
                Label.created += 1
                self.text = k.get("text", "")
                self.destroyed = False

            def grid(self, *a, **k): pass
            def grid_remove(self): pass
            def configure(self, **k): self.text = k.get("text", self.text)
            def destroy(self): self.destroyed = True

        ctk = MagicMock()
        ctk.CTkLabel = Label
        d = Dashboard.__new__(Dashboard)
        d.ctk = ctk
        d._font = lambda *a, **k: None
        pool, card = [], object()
        d._sync_rows(card, pool, [("A", "1", "x"), ("B", "2", "x")], 150, False, 5)
        made = Label.created
        d._sync_rows(card, pool, [("A", "1", "x"), ("B", "3", "x")], 150, False, 5)
        self.assertEqual(Label.created, made)                # nothing rebuilt
        self.assertEqual(pool[1]["right"].text, "3")         # only the changed text was set
        d._sync_rows(card, pool, [("A", "1", "x")], 150, False, 5)
        self.assertIsNone(pool[1]["shown"])                  # extra rows are hidden, not destroyed


if __name__ == "__main__":
    unittest.main()


class NewOverlayDiscoveryTests(unittest.TestCase):
    def test_unknown_overlay_becomes_a_command(self):
        from control.matcher import Matcher
        from control.vc_overlays import discover
        rows = [{"id": "navigation", "name": "Navigation HUD"}, {"id": "fuel-scoop", "name": "Fuel Scoop Timer"},
                {"id": "../evil", "name": "x"}]
        found = discover(rows)
        self.assertEqual([f[0] for f in found], ["fuel-scoop"])
        from control.catalog import overlay_command
        m = Matcher()
        self.assertTrue(m.add(overlay_command(*found[0])))
        hit = m.match("show the fuel scoop timer overlay")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.command.service, ("voidcompass", "fuel-scoop"))
        self.assertFalse(m.add(overlay_command(*found[0])))

    def test_known_overlays_are_not_added_twice(self):
        from control.vc_overlays import OVERLAYS, discover
        self.assertEqual(discover([{"id": o[0], "name": o[1]} for o in OVERLAYS]), [])


class KeyClashTests(unittest.TestCase):
    def book(self, xml):
        from control.binds import BindingBook
        d = Path(tempfile.mkdtemp())
        (d / "A.4.0.binds").write_text(xml)
        (d / "StartPreset.start").write_text("A\n")
        return BindingBook(d)

    def test_select_on_enter_clashes_with_quick_comms(self):
        book = self.book('<?xml version="1.0"?><Root>'
                         '<UI_Select><Primary Device="Keyboard" Key="Key_Enter" /><Secondary Device="{NoDevice}" Key="" /></UI_Select>'
                         '<QuickCommsPanel><Primary Device="Keyboard" Key="Key_Enter" /></QuickCommsPanel>'
                         '<QuickCommsPanel_Humanoid><Primary Device="Keyboard" Key="Key_Enter" /></QuickCommsPanel_Humanoid>'
                         '<UI_Back><Primary Device="Keyboard" Key="Key_Backspace" /></UI_Back></Root>')
        self.assertEqual(book.conflicts("UI_Select"), ["QuickCommsPanel"])
        self.assertEqual(book.conflicts("UI_Back"), [])
        self.assertEqual(book.conflicts("Nothing"), [])
