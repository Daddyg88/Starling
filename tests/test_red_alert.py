"""Red alert (0.87.0): the switch, her voice, the speed, the chatter, the glow numbers."""
import unittest

from core import red_alert
from core.red_alert import RedAlert
from tests.test_phase6b import make_settings
from ui import red_alert_overlay as glow


class Thing:
    pass


class Narrate:
    def __init__(self):
        self.said = []

    def say(self, key, fields=None):
        self.said.append(key)


class Switch(unittest.TestCase):
    def build(self, **values):
        self.speech, self.kokoro, self.flavour, self.narrator = Thing(), Thing(), Thing(), Narrate()
        self.now = [100.0]
        return RedAlert(make_settings(**values), lambda: self.speech, lambda: self.kokoro, lambda: self.flavour, self.narrator, clock=lambda: self.now[0])

    def test_on_changes_everything_and_off_puts_it_back(self):
        a = self.build()
        self.assertTrue(a.turn_on())
        self.assertTrue(self.speech.alert and self.flavour.red_alert)
        self.assertEqual(self.kokoro.speed_boost, 1.2)
        self.assertEqual(self.narrator.said, ["RedAlert_On"])
        self.assertTrue(a.turn_off())
        self.assertFalse(self.speech.alert or self.flavour.red_alert)
        self.assertEqual(self.kokoro.speed_boost, 1.0)
        self.assertEqual(self.narrator.said, ["RedAlert_On", "RedAlert_Off"])

    def test_twice_does_nothing_twice(self):
        a = self.build()
        a.turn_on()
        self.assertFalse(a.turn_on())
        self.assertEqual(self.narrator.said, ["RedAlert_On"])
        self.assertFalse(self.build().turn_off())

    def test_speed_setting_is_followed_and_limited(self):
        a = self.build(red_alert={"speed": 1.75})
        a.turn_on()
        self.assertEqual(self.kokoro.speed_boost, 1.75)
        self.assertEqual(red_alert.speed_setting(make_settings(red_alert={"speed": 9})), 2.0)
        self.assertEqual(red_alert.speed_setting(make_settings(red_alert={"speed": 0.2})), 1.0)
        self.assertEqual(red_alert.speed_setting(make_settings(red_alert={"speed": "x"})), 1.2)

    def test_it_stands_down_by_itself(self):
        a = self.build(red_alert={"minutes": 10})
        a.turn_on()
        self.now[0] += 590
        a.tick()
        self.assertTrue(a.active)
        self.now[0] += 20
        a.tick()
        self.assertFalse(a.active)
        self.assertFalse(self.speech.alert)

    def test_never_means_never(self):
        a = self.build(red_alert={"minutes": 0})
        a.turn_on()
        self.now[0] += 100000
        a.tick()
        self.assertTrue(a.active)

    def test_missing_parts_do_not_break_it(self):
        a = RedAlert(make_settings(), lambda: None, lambda: None, lambda: None, None)
        self.assertTrue(a.turn_on())
        self.assertTrue(a.turn_off())

    def test_what_she_understands(self):
        a = self.build()
        for text in ("red alert", "Red alert!", "go to red alert", "battle stations", "engage red alert"):
            a.turn_off(False)
            self.assertEqual(a.try_handle(text), "Red alert.", text)
            self.assertTrue(a.active)
        self.assertEqual(a.try_handle("red alert"), "Red alert is already on.")
        for text in ("stand down", "all clear", "cancel red alert", "red alert off", "Stand down red alert."):
            a.turn_on(False)
            self.assertEqual(a.try_handle(text), "Standing down.", text)
            self.assertFalse(a.active)
        self.assertEqual(a.try_handle("stand down"), "There is no red alert on.")
        self.assertIsNone(a.try_handle("open the galaxy map"))
        self.assertIsNone(a.try_handle("what is a red giant"))


class Effects(unittest.TestCase):
    def test_low_priority_chatter_is_dropped_in_alert(self):
        from tts.speech_manager import SpeechManager
        speech = SpeechManager({}, make_settings())
        speech._running = True
        self.assertTrue(speech.say(text="idle chat", priority="low"))
        speech._queue.clear()
        speech.alert = True
        self.assertFalse(speech.say(text="idle chat", priority="low"))
        self.assertTrue(speech.say(text="Shields down", priority="critical"))
        self.assertTrue(speech.say(text="Gear away", priority="normal"))

    def test_no_remarks_or_pet_names_in_alert(self):
        from personality.flavour import Flavour

        class Dialogue:
            def pick(self, *a, **k):
                return None
        f = Flavour(Dialogue(), make_settings(personality={"remarks": "often", "pet_names": True}))
        f.red_alert = True
        for _ in range(30):
            self.assertEqual(f.apply("Docked, Commander."), "Docked, Commander.")

    def test_voice_speed_is_multiplied_and_capped(self):
        from tts.kokoro_tts import speed_from_rate
        self.assertEqual(round(min(2.0, speed_from_rate(0) * 1.5), 2), 1.5)
        self.assertEqual(min(2.0, speed_from_rate(10) * 2.0), 2.0)

    def test_voice_lines_exist(self):
        import json
        from pathlib import Path
        pools = json.loads(Path("voicepacks/default/commands.json").read_text(encoding="utf-8"))
        self.assertTrue(pools["RedAlert_On"] and pools["RedAlert_Off"])


class GlowNumbers(unittest.TestCase):
    def test_it_is_steady_and_gets_stronger_by_choice(self):
        self.assertFalse(hasattr(glow, "pulse_alpha"))
        self.assertLess(glow.edge_alpha("Soft"), glow.edge_alpha("Medium"))
        self.assertLess(glow.edge_alpha("Medium"), glow.edge_alpha("Strong"))
        self.assertEqual(glow.edge_alpha("nonsense"), glow.edge_alpha("Medium"))

    def test_it_is_a_filter_not_a_wall(self):
        for name in glow.STRENGTH:
            self.assertLessEqual(glow.tint_alpha(name), 0.16)
            self.assertLessEqual(glow.edge_alpha(name), 0.30)
            self.assertGreater(glow.tint_alpha(name), 0.05)            # strong enough to read as a red filter

    def test_bands_go_from_bright_edge_to_dark_inside_and_stay_thin(self):
        rings, each = glow.bands(1920, 1080)
        self.assertEqual(len(rings), glow.BANDS)
        self.assertEqual(rings[0][:2], (0, 0))
        self.assertEqual(rings[0][2:4], (1920, 1080))
        self.assertGreater(int(rings[0][4][1:3], 16), int(rings[-1][4][1:3], 16))
        self.assertLessEqual(glow.band_width(1920, 1080), 30)         # thin: about 2.5% of the height
        self.assertGreaterEqual(glow.band_width(800, 600), 20)

    def test_four_k_scales(self):
        self.assertGreater(glow.band_width(3840, 2160), glow.band_width(1920, 1080))


class CombatMode(unittest.TestCase):
    def test_red_alert_asks_for_combat_mode_once_and_it_can_be_switched_off(self):
        calls = []
        a = RedAlert(make_settings(), lambda: None, lambda: None, lambda: None, None, combat_mode=lambda: calls.append(1))
        a.turn_on()
        a.turn_on()                                                    # already on: not asked again
        self.assertEqual(calls, [1])
        b = RedAlert(make_settings(red_alert={"combat_mode": False}), lambda: None, lambda: None, lambda: None, None, combat_mode=lambda: calls.append(2))
        b.turn_on()
        self.assertEqual(calls, [1])

    def test_a_failing_combat_mode_does_not_stop_red_alert(self):
        def boom():
            raise RuntimeError("no key")
        a = RedAlert(make_settings(), lambda: None, lambda: None, lambda: None, None, combat_mode=boom)
        self.assertTrue(a.turn_on())
        self.assertTrue(a.active)

    def test_the_hud_command_it_uses_exists(self):
        from tests import test_macros
        r = test_macros.MacroTests().build()
        self.assertEqual(r.matcher.match("switch to combat mode").command.id, "hud_mode")


if __name__ == "__main__":
    unittest.main()


class NeverTakesTheMouse(unittest.TestCase):
    def test_the_overlay_hardens_and_shows_without_activating(self):
        """0.87.2: the first version took the game's focus (mouse cursor appeared, clicks blocked). Check the safe Windows calls are
        the ones used, with a fake user32, since the real one only exists on Windows."""
        import sys
        import types
        calls = []

        class User32:
            def GetParent(self, h):
                return 0

            def GetWindowLongW(self, h, i):
                calls.append(("get", i))
                return 0

            def SetWindowLongW(self, h, i, v):
                calls.append(("set", i, v))

            def ShowWindow(self, h, c):
                calls.append(("show", c))

            def SetWindowPos(self, h, after, x, y, w, hh, flags):
                calls.append(("pos", after, flags))

        class Window:
            def winfo_id(self):
                return 7

        fake = types.SimpleNamespace(windll=types.SimpleNamespace(user32=User32()))
        real = sys.modules.get("ctypes")
        overlay = glow.RedAlertOverlay.__new__(glow.RedAlertOverlay)
        import ctypes
        old = getattr(ctypes, "windll", None)
        ctypes.windll = fake.windll
        try:
            overlay._harden(Window())
            overlay._put_on_top_without_focus(Window())
        finally:
            if old is None:
                del ctypes.windll
            else:
                ctypes.windll = old
        setcall = [c for c in calls if c[0] == "set"][0]
        self.assertTrue(setcall[2] & 0x20)               # clicks go through
        self.assertTrue(setcall[2] & 0x08000000)         # never the active window
        self.assertIn(("show", 4), calls)                # SW_SHOWNOACTIVATE, not a normal show
        pos = [c for c in calls if c[0] == "pos"][0]
        self.assertTrue(pos[2] & 0x10)                   # SWP_NOACTIVATE
