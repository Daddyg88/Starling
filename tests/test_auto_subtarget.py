"""Red alert picks the power plant by itself once the target ship has been scanned."""

import unittest
from types import SimpleNamespace

from control.auto_subtarget import AutoSubTarget, COOLDOWN_SECONDS


class FakeRunner:
    def __init__(self):
        self.calls = []

    def run_text(self, text, **kwargs):
        self.calls.append((text, kwargs))


class FakeSettings:
    def __init__(self, on=True):
        self.on = on

    def get(self, key, default=None):
        return self.on if key == "red_alert.auto_power_plant" else default


def scanned(ship="Anaconda", pilot="Bob", stage=3, **extra):
    entry = {"event": "ShipTargeted", "TargetLocked": True, "Ship": ship, "PilotName": pilot, "ScanStage": stage}
    entry.update(extra)
    return entry


class Base(unittest.TestCase):
    def setUp(self):
        self.runner = FakeRunner()
        self.red = SimpleNamespace(active=True)
        self.state = SimpleNamespace(in_supercruise=False, docked=False, on_foot=False)
        self.now = [100.0]
        self.settings = FakeSettings()
        self.auto = AutoSubTarget(self.settings, lambda: self.runner, lambda: self.red, lambda: self.state,
                                  clock=lambda: self.now[0], start=lambda job: job())


class Tests(Base):
    def test_a_finished_scan_during_red_alert_picks_the_power_plant(self):
        self.auto.on_entry(scanned(), False)
        self.assertEqual(self.runner.calls, [("target power plant", {"speak": False, "speak_unknown": False, "auto": True})])

    def test_only_once_per_ship(self):
        self.auto.on_entry(scanned(), False)
        self.now[0] += 60
        self.auto.on_entry(scanned(), False)                 # the same ship again (the game repeats the line)
        self.assertEqual(len(self.runner.calls), 1)
        self.now[0] += 60
        self.auto.on_entry(scanned(ship="Viper", pilot="Al"), False)
        self.assertEqual(len(self.runner.calls), 2)

    def test_losing_the_lock_makes_the_same_ship_new_again(self):
        self.auto.on_entry(scanned(), False)
        self.auto.on_entry({"event": "ShipTargeted", "TargetLocked": False}, False)
        self.now[0] += COOLDOWN_SECONDS + 1
        self.auto.on_entry(scanned(), False)
        self.assertEqual(len(self.runner.calls), 2)

    def test_nothing_without_red_alert_or_when_switched_off(self):
        self.red.active = False
        self.auto.on_entry(scanned(), False)
        self.red.active = True
        self.settings.on = False
        self.auto.on_entry(scanned(), False)
        self.assertEqual(self.runner.calls, [])

    def test_nothing_before_the_scan_is_finished_or_when_a_part_is_already_picked(self):
        self.auto.on_entry(scanned(stage=1), False)
        self.auto.on_entry(scanned(stage=2), False)
        self.auto.on_entry(scanned(Subsystem="$int_engine_size5_class5_name;"), False)
        self.assertEqual(self.runner.calls, [])

    def test_nothing_in_supercruise_docked_on_foot_or_when_replaying_the_journal(self):
        for field in ("in_supercruise", "docked", "on_foot"):
            setattr(self.state, field, True)
            self.auto.on_entry(scanned(), False)
            setattr(self.state, field, False)
        self.auto.on_entry(scanned(), True)                    # silent: she is only catching up on an old journal
        self.assertEqual(self.runner.calls, [])

    def test_other_events_are_ignored(self):
        self.auto.on_entry({"event": "Docked"}, False)
        self.assertEqual(self.runner.calls, [])


class Setting(unittest.TestCase):
    def test_it_is_on_by_default_and_has_a_switch_on_the_settings_page(self):
        from core.settings import DEFAULTS
        self.assertTrue(DEFAULTS["red_alert"]["auto_power_plant"])
        source = open("ui/settings_model.py", encoding="utf-8").read()
        self.assertIn('"red_alert.auto_power_plant"', source)


if __name__ == "__main__":
    unittest.main()
