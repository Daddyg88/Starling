import unittest

from control.auto_shields import AutoShields
from events.shield_state import ShieldState


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class Book:
    def lookup(self, action):
        return "k", ""


class Sender:
    def send(self, stroke):
        return None


class Settings:
    def get(self, key, default=None):
        return True


class OwnPressTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.a = AutoShields(Settings(), Book(), Sender(), clock=self.clock)
        ShieldState.own_press = self.a.caused

    def tearDown(self):
        ShieldState.own_press = None

    def test_lowering_is_silent_once(self):
        self.a.up = True
        self.a._lower()
        self.clock.t += 1
        self.assertTrue(ShieldState().handle({"ShieldsUp": False}).get("_silent"))
        self.assertFalse(ShieldState().handle({"ShieldsUp": False}).get("_silent"))     # a second one is real news

    def test_raising_is_silent(self):
        self.a._raise("weapon")
        self.assertTrue(ShieldState().handle({"ShieldsUp": True}).get("_silent"))

    def test_other_direction_or_too_late_is_announced(self):
        self.a.up = True
        self.a._lower()
        self.assertFalse(ShieldState().handle({"ShieldsUp": True}).get("_silent"))
        self.a.up = True
        self.a._lower()
        self.clock.t += 30
        self.assertFalse(ShieldState().handle({"ShieldsUp": False}).get("_silent"))

    def test_no_hook_changes_nothing(self):
        ShieldState.own_press = None
        self.assertEqual(ShieldState().handle({"ShieldsUp": False}), {"ShieldsUp": False})


if __name__ == "__main__":
    unittest.main()
