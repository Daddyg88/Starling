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
        self.assertEqual(self.kokoro.speed_boost, 1.5)
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
        self.assertEqual(red_alert.speed_setting(make_settings(red_alert={"speed": "x"})), 1.5)

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
    def test_pulse_swings_between_low_and_high(self):
        values = [glow.pulse_alpha("Medium", t / 100.0) for t in range(0, 240)]
        self.assertAlmostEqual(min(values), 0.16, places=2)
        self.assertAlmostEqual(max(values), 0.45, places=2)
        self.assertGreater(glow.pulse_alpha("Strong", 0.3), glow.pulse_alpha("Soft", 0.3))
        self.assertEqual(glow.pulse_alpha("nonsense", 0.0), glow.pulse_alpha("Medium", 0.0))

    def test_tint_is_faint(self):
        for name in glow.STRENGTH:
            self.assertLess(glow.tint_alpha(name), 0.12)

    def test_bands_go_from_bright_edge_to_dark_inside(self):
        rings, each = glow.bands(1920, 1080)
        self.assertEqual(len(rings), glow.BANDS)
        self.assertEqual(rings[0][:2], (0, 0))
        self.assertEqual(rings[0][2:4], (1920, 1080))
        self.assertGreater(int(rings[0][4][1:3], 16), int(rings[-1][4][1:3], 16))
        self.assertLess(rings[-1][0] + each, 1080 // 2)                 # the frame never reaches the middle
        self.assertGreaterEqual(glow.band_width(800, 600), 40)

    def test_four_k_scales(self):
        self.assertGreater(glow.band_width(3840, 2160), glow.band_width(1920, 1080))


if __name__ == "__main__":
    unittest.main()
