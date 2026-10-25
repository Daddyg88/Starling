import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from control.auto_shields import AutoShields
from control.onfoot_care import OnFootCare
from journal import backpack


class Settings:
    def __init__(self, **v):
        self.v = v

    def get(self, key, default=None):
        return self.v.get(key.split(".")[-1], default)


class Book:
    def lookup(self, action):
        return (action, "")


class Sender:
    def __init__(self):
        self.sent = []

    def send(self, stroke, hold=None):
        self.sent.append(stroke)
        return None


class Narrator:
    def __init__(self):
        self.said = []

    def say(self, key, fields=None):
        self.said.append((key, fields))


def foot(weapon="", health=1.0, on=True):
    return SimpleNamespace(status_flags2=1 if on else 0, selected_weapon=weapon, health=health)


def write_pack(folder, **counts):
    (Path(folder) / "Backpack.json").write_text(json.dumps(
        {"Consumables": [{"Name": n, "Count": c} for n, c in counts.items()]}), encoding="utf-8")


class CareTests(unittest.TestCase):
    def make(self, pack=None, **settings):
        self.dir = Path(tempfile.mkdtemp())
        if pack is not None:
            write_pack(self.dir, **pack)
        self.sender, self.narrator, self.clock = Sender(), Narrator(), [0.0]
        return OnFootCare(Settings(**settings), Book(), self.sender, self.narrator, lambda: self.dir, clock=lambda: self.clock[0])

    def test_medpack_at_20_percent_or_below_only(self):
        c = self.make({"healthpack": 2}, auto_health=True)
        c.check(foot("", 0.5))
        c.check(foot("", 0.21))
        self.assertEqual(self.sender.sent, [])
        c.check(foot("", 0.2))
        self.assertEqual(self.sender.sent, ["HumanoidHealthPack"])
        c.check(foot("", 0.1))                                   # inside the cooldown
        self.assertEqual(len(self.sender.sent), 1)
        self.clock[0] = 10
        c.check(foot("", 0.1))
        self.assertEqual(len(self.sender.sent), 2)

    def test_nothing_is_pressed_when_the_switch_is_off(self):
        c = self.make({"healthpack": 2})
        c.check(foot("", 0.05))
        self.assertEqual(self.sender.sent, [])

    def test_no_medpack_left_means_no_press_and_she_says_so(self):
        c = self.make({"healthpack": 0}, auto_health=True)
        c.check(foot("", 0.1))
        self.assertEqual(self.sender.sent, [])
        self.assertEqual(self.narrator.said[0][0], "OnFootNoSupplies")

    def test_energy_cell_when_health_first_drops(self):
        c = self.make({"energycell": 1}, auto_battery=True)
        c.check(foot("rifle", 1.0))
        self.assertEqual(self.sender.sent, [])
        c.check(foot("rifle", 0.9))
        self.assertEqual(self.sender.sent, ["HumanoidBattery"])

    def test_not_on_foot_does_nothing(self):
        c = self.make({"healthpack": 2}, auto_health=True)
        c.check(foot("", 0.05, on=False))
        self.assertEqual(self.sender.sent, [])

    def test_last_grenade_is_called_out_once(self):
        c = self.make({"amm_grenade_frag": 2, "amm_grenade_emp": 1})
        c.check(foot("rifle"))                                   # baseline
        write_pack(self.dir, amm_grenade_frag=1, amm_grenade_emp=1)
        (self.dir / "Backpack.json").touch()
        c.check(foot("rifle"))
        self.assertEqual(self.narrator.said, [])                 # one frag left: not the last
        import os
        write_pack(self.dir, amm_grenade_frag=1, amm_grenade_emp=0)
        os.utime(self.dir / "Backpack.json", ns=(10 ** 18, 10 ** 18))
        c.check(foot("rifle"))
        self.assertEqual(self.narrator.said, [("OnFootLastGrenade", {"grenade": "EMP"})])
        c.check(foot("rifle"))
        self.assertEqual(len(self.narrator.said), 1)

    def test_emptying_your_backpack_with_no_weapon_out_is_not_a_throw(self):
        c = self.make({"amm_grenade_frag": 1})
        c.check(foot(""))
        import os
        write_pack(self.dir, amm_grenade_frag=0)
        os.utime(self.dir / "Backpack.json", ns=(10 ** 18, 10 ** 18))
        c.check(foot(""))
        self.assertEqual(self.narrator.said, [])

    def test_backpack_reader(self):
        d = Path(tempfile.mkdtemp())
        self.assertIsNone(backpack.read_counts(d))
        write_pack(d, healthpack=3, amm_grenade_frag=1)
        counts = backpack.read_counts(d)
        self.assertEqual(backpack.count_matching(counts, "healthpack"), 3)
        self.assertEqual(backpack.grenade_label("amm_grenade_shield"), "shield")


class CombatShieldTests(unittest.TestCase):
    def make(self):
        self.sender, self.clock = Sender(), [0.0]
        return AutoShields(Settings(auto_shields=True), Book(), self.sender, clock=lambda: self.clock[0])

    def test_a_kill_bond_on_foot_raises_and_holstering_does_not_lower(self):
        a = self.make()
        a.check(foot(""))
        a.on_combat_event()
        a.check(foot(""))
        self.assertEqual(self.sender.sent, ["HumanoidToggleShieldsButton"])
        a.check(foot("rifle"))
        a.check(foot(""))
        self.assertEqual(len(self.sender.sent), 1)               # holstered inside the fight: still up

    def test_shields_come_down_when_the_fight_is_over_and_no_weapon_is_out(self):
        a = self.make()
        a.check(foot(""))
        a.on_combat_event()
        a.check(foot(""))
        self.clock[0] = 200
        a.check(foot(""))
        self.assertEqual(len(self.sender.sent), 2)

    def test_combat_bond_while_not_on_foot_is_ignored(self):
        a = self.make()
        a.check(foot("", on=False))
        a.on_combat_event()
        a.check(foot("", on=False))
        self.assertEqual(self.sender.sent, [])

    def test_damage_starts_the_fight(self):
        a = self.make()
        a.check(foot("", 1.0))
        a.check(foot("", 0.8))
        self.assertTrue(a.fighting())


class PageTests(unittest.TestCase):
    def test_switches_and_lines_exist(self):
        from ui.settings_model import build_pages
        keys = [f.key for p in build_pages() if p.id == "onfoot" for f in p.fields]
        for k in ("onfoot.auto_health", "onfoot.auto_battery", "onfoot.last_grenade_callout"):
            self.assertIn(k, keys)
        lines = json.loads(Path("voicepacks/default/onfoot.json").read_text(encoding="utf-8"))
        self.assertIn("OnFootLastGrenade", lines)


if __name__ == "__main__":
    unittest.main()
