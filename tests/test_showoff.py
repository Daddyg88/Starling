import unittest
from types import SimpleNamespace

from control.catalog import SHOWOFF_MACRO
from control.macros import parse_macro, actions_in
from core import paths
from personality.dialogue import DialogueManager
from tests.test_commands import FakeSpeech
from tests.test_macros import ALL, MacroTests


class ShowOffTests(unittest.TestCase):
    def test_the_macro_parses_and_every_key_is_a_screen_key(self):
        steps = parse_macro(list(SHOWOFF_MACRO))
        self.assertLessEqual(len(steps), 60)
        flight = {"ThrustForward", "SetSpeedZero", "DeployHardpointToggle", "ToggleCargoScoop", "LandingGearToggle", "UseShieldCell"}
        self.assertFalse(flight & set(actions_in(steps)))
        self.assertTrue(set(actions_in(steps)) <= {"GalaxyMapOpen", "FocusLeftPanel", "FocusRightPanel", "CycleNextPanel",
                                                  "CyclePreviousPanel", "UI_Back"})

    def test_every_talk_line_exists(self):
        known = set(DialogueManager(paths.VOICEPACKS_DIR / "default").load().lines)
        for kind, key in [s for s in parse_macro(list(SHOWOFF_MACRO)) if s[0] == "talk"]:
            self.assertIn(key, known)

    def test_many_ways_to_ask(self):
        r = MacroTests().build()
        for text in ("show off", "go on show off", "show chat what you can do", "show us what you can do", "impress chat",
                     "show off for the stream", "show your skills"):
            m = r.matcher.match(text)
            self.assertIsNotNone(m, text)
            self.assertEqual(m.command.id, "show_off", text)

    def test_what_can_you_do_is_still_a_spoken_answer_not_the_show(self):
        r = MacroTests().build()
        m = r.matcher.match("what can you do")
        self.assertTrue(m is None or m.command.id != "show_off")

    def test_she_talks_and_presses_only_screen_keys_and_leaves_open_screens_closed(self):
        t = MacroTests()
        r = t.build(table={**ALL, "GalaxyMapOpen": ALL["FocusLeftPanel"]})
        said = []
        r.speech = SimpleNamespace(say=lambda **kw: said.append(kw["text"]), wait_until_idle=lambda timeout=0: True)
        r.state_provider = lambda: SimpleNamespace(gui_focus="?", status_seen=False)
        r.run_text("show off")
        self.assertGreaterEqual(len(said), 8)
        self.assertGreater(len(t.sender.pressed), 8)

    def test_the_screen_chatter_is_muted_and_talk_lines_are_plain(self):
        t = MacroTests()
        r = t.build(table={**ALL, "GalaxyMapOpen": ALL["FocusLeftPanel"]})
        muted = []
        r.echo = SimpleNamespace(mute=lambda names, seconds: muted.append((tuple(names), seconds)), expect=lambda *a, **k: None,
                                 cancel=lambda *a, **k: None)
        r.flavour = SimpleNamespace(apply=lambda text, _p: text + " EXTRA", rename=lambda x: x)
        said = []
        r.speech = SimpleNamespace(say=lambda **kw: said.append(kw["text"]), wait_until_idle=lambda timeout=0: True)
        r.state_provider = lambda: SimpleNamespace(gui_focus="?", status_seen=False)
        r.run_text("show off")
        self.assertIn("GalaxyMapOpened", muted[0][0])
        self.assertIn("ScreenClosed", muted[0][0])
        self.assertGreaterEqual(muted[0][1], 120)
        self.assertTrue(said)
        self.assertFalse([x for x in said if "EXTRA" in x and x.startswith("Right.")])      # the talk lines skip the flavour

    def test_leave_presses_only_when_that_screen_is_open_or_unknown(self):
        self.assertEqual(parse_macro(["leave UI_Back 2"]), [("leave", "UI_Back", 2)])
        t = MacroTests()
        for gui, expected in ((2, 1), (0, 0), (6, 0), ("?", 1)):
            r = t.build()
            r.state_provider = lambda g=gui: SimpleNamespace(gui_focus=g, status_seen=True) if g != "?" else SimpleNamespace(gui_focus=0, status_seen=False)
            r.macro_steps = lambda command: ["leave UI_Back 2"]
            r.run_text("request docking")
            self.assertEqual(len(t.sender.pressed), expected, gui)

    def test_talk_parses_and_finish_waits(self):
        self.assertEqual(parse_macro(["talk ShowOff_Map", "finish"]), [("talk", "ShowOff_Map"), ("finish",)])
        with self.assertRaises(ValueError):
            parse_macro(["talk bad key!"])


if __name__ == "__main__":
    unittest.main()
