"""Auto honk tests: it holds the right fire button on arrival, and only when it is safe."""

import unittest

from control.autohonk import AutoHonk, HARDPOINTS_BIT
from control.binds import Keystroke
from core.event_bus import EventBus
from journal.game_state import GameState
from tests.test_commands import FakeBook, FakeSender, FakeSpeech
from tests.test_phase6b import make_settings


class HoldSender(FakeSender):
    def __init__(self):
        super().__init__()
        self.holds = []

    def send(self, keystroke, hold=None):
        self.holds.append(hold)
        return super().send(keystroke)


class AutoHonkTests(unittest.TestCase):
    def build(self, mode="primary", table=None, flags=0, **values):
        self.settings = make_settings(autohonk__mode=mode, **values)
        self.state = GameState()
        self.state.status_flags = flags
        self.sender, self.speech = HoldSender(), FakeSpeech()
        book = FakeBook(table if table is not None else
                        {"PrimaryFire": (Keystroke("Key_1"), ""), "SecondaryFire": (Keystroke("Key_2"), "")})
        self.now = [0.0]
        self.honk = AutoHonk(EventBus(), self.settings, book, self.sender, lambda: self.state, speech=self.speech,
                             sleep=lambda s: None, clock=lambda: self.now[0], spawn=lambda f: f())
        return self.honk

    def test_off_by_default(self):
        from core.settings import DEFAULTS
        self.assertEqual(DEFAULTS["autohonk"]["mode"], "off")
        self.build(mode="off").on_jump(None)
        self.assertEqual(self.sender.pressed, [])

    def test_primary_holds_the_primary_fire_key(self):
        self.build("primary").on_jump(None)
        self.assertEqual(self.sender.pressed, [Keystroke("Key_1")])
        self.assertEqual(self.sender.holds, [6.0])

    def test_secondary_holds_the_secondary_fire_key(self):
        self.build("secondary").on_jump(None)
        self.assertEqual(self.sender.pressed, [Keystroke("Key_2")])

    def test_it_fires_on_the_real_jump_event(self):
        honk = self.build("primary")
        honk.attach()
        honk.bus.publish("FSDJump", {"StarSystem": "Sol"}, "normal")
        self.assertEqual(len(self.sender.pressed), 1)

    def test_never_while_hardpoints_are_out(self):
        self.build("primary", flags=1 << HARDPOINTS_BIT).on_jump(None)
        self.assertEqual(self.sender.pressed, [])

    def test_a_joystick_only_button_is_explained_once(self):
        honk = self.build("primary", table={"PrimaryFire": (None, "joystick_only")})
        honk.on_jump(None)
        self.now[0] = 100
        honk.on_jump(None)
        self.assertEqual(self.sender.pressed, [])
        self.assertEqual(len(self.speech.said), 1)
        self.assertIn("keyboard", self.speech.said[0]["text"])

    def test_two_arrivals_in_a_row_honk_once(self):
        honk = self.build("primary")
        honk.on_jump(None)
        self.now[0] = 5
        honk.on_jump(None)
        self.assertEqual(len(self.sender.pressed), 1)

    def test_the_dashboard_has_the_dropdown(self):
        from ui.settings_model import build_pages
        keys = {f.key: f for page in build_pages() for f in page.fields}
        self.assertEqual([v for _l, v in keys["autohonk.mode"].choices], ["off", "primary", "secondary"])


if __name__ == "__main__":
    unittest.main()


class HonkExtrasTests(AutoHonkTests):
    """0.28.0: honk even when jump speech is off, switch to analysis mode if needed, and a test button."""

    def test_the_arrival_signal_also_starts_a_honk(self):
        honk = self.build("primary")
        honk.attach()
        honk.bus.publish("journal.arrived", {"StarSystem": "Sol"}, "low")
        self.assertEqual(len(self.sender.pressed), 1)

    def test_combat_mode_switches_to_analysis_and_back(self):
        from control.autohonk import ANALYSIS_BIT, HUD_MODE_ACTION
        honk = self.build("primary", table={"PrimaryFire": (Keystroke("Key_1"), ""), HUD_MODE_ACTION: (Keystroke("Key_h"), "")})
        self.state.status_seen = True
        honk.on_jump(None)
        self.assertEqual([k.key for k in self.sender.pressed], ["Key_h", "Key_1", "Key_h"])
        self.sender.pressed.clear()
        self.now[0] += 100
        self.state.status_flags = 1 << ANALYSIS_BIT              # already in analysis mode: no switching
        honk.on_jump(None)
        self.assertEqual([k.key for k in self.sender.pressed], ["Key_1"])

    def test_no_switch_when_the_mode_key_is_missing_or_status_unknown(self):
        honk = self.build("primary")
        self.state.status_seen = True
        honk.on_jump(None)
        self.assertEqual([k.key for k in self.sender.pressed], ["Key_1"])

    def test_test_button_explains_and_speaks_the_result(self):
        honk = self.build("primary", table={})
        said = honk.test_now(delay=0)
        self.assertIn("Click into Elite", said)
        self.assertEqual(honk.last_result, "unbound")
        spoken = [call["text"] for call in self.speech.said]
        self.assertEqual(len(spoken), 1)                       # the test result only, not the one-time warning as well
        self.assertIn("KEYBOARD key", spoken[0])
