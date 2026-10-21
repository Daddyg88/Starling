import json
import unittest
from types import SimpleNamespace

from control.binds import BindingBook, parse_binds
from control.combat_assist import CombatAssist, fire_specs, key_spec_from_elite, DEFAULT_PIPS_UP, DEFAULT_PIPS_DOWN
from control.inputs import JoyDevice
from core.event_bus import EventBus
from personality import line_keys
from tests.helpers import make_processor

BINDS = """<Root>
<PrimaryFire><Primary Device="06A3075C" Key="Joy_1"/><Secondary Device="Keyboard" Key="Key_Space"/></PrimaryFire>
<SecondaryFire><Primary Device="SaitekX52" Key="Joy_2"/><Secondary Device="{NoDevice}" Key=""/></SecondaryFire>
<IncreaseWeaponsPower><Primary Device="Keyboard" Key="Key_A"/></IncreaseWeaponsPower>
<IncreaseSystemsPower><Primary Device="Keyboard" Key="Key_B"/></IncreaseSystemsPower>
<IncreaseEnginesPower><Primary Device="Keyboard" Key="Key_C"/></IncreaseEnginesPower>
<ResetPowerDistribution><Primary Device="Keyboard" Key="Key_D"/></ResetPowerDistribution>
<UseShieldCell><Primary Device="Keyboard" Key="Key_E"/></UseShieldCell>
<DeployHeatSink><Primary Device="Keyboard" Key="Key_F"/></DeployHeatSink>
</Root>"""


class Book(BindingBook):
    def __init__(self):
        self._actions = parse_binds(BINDS)

    def refresh(self):
        return True


class Sender:
    def __init__(self):
        self.pressed = []
        self.problem = ""

    def send(self, stroke, hold=None):
        self.pressed.append(stroke.key.replace("Key_", ""))
        return self.problem


class Reader:
    def __init__(self):
        self.down = set()
        self.stick = JoyDevice(0, 0x06A3, 0x075C, "Saitek X52", 32)

    def is_down(self, spec):
        return spec in self.down

    def x52_devices(self):
        return [self.stick]


class Settings:
    def __init__(self, **values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


class Clock:
    now = 100.0

    def __call__(self):
        return self.now


class Base(unittest.TestCase):
    def setUp(self):
        self.bus, self.sender, self.reader, self.clock = EventBus(), Sender(), Reader(), Clock()
        self.state = SimpleNamespace(status_flags=1 << 6)           # hardpoints out
        self.settings = Settings()
        self.assist = CombatAssist(self.bus, self.settings, Book(), self.sender, self.reader, lambda: self.state,
                                   clock=self.clock, sleep=lambda s: None)
        self.bus_threads = []
        # run key presses on the spot instead of in threads
        import threading
        self._thread = threading.Thread

        def fake(target=None, name="", **k):
            if name == "combat-assist":                    # the polling loop is driven by hand in these tests
                return SimpleNamespace(start=lambda: None, join=lambda *a, **k: None)
            return SimpleNamespace(start=lambda: target(), join=lambda *a, **k: None)
        threading.Thread = fake
        self.addCleanup(lambda: setattr(threading, "Thread", self._thread))

    def keys(self):
        return "".join(self.sender.pressed)


class FireButtonTests(unittest.TestCase):
    def test_key_names(self):
        self.assertEqual(key_spec_from_elite("Key_Space"), "key:Space")
        self.assertEqual(key_spec_from_elite("Key_Numpad_1"), "key:Numpad1")
        self.assertIsNone(key_spec_from_elite("Key_Nothing"))

    def test_buttons_come_from_the_controls_file(self):
        specs = fire_specs(Book(), Reader())
        self.assertIn("joy:06A3:075C:1", specs)
        self.assertIn("joy:06A3:075C:2", specs)             # "SaitekX52" is found by name
        self.assertIn("key:Space", specs)


class PipTests(Base):
    def test_pips_follow_the_trigger(self):
        self.assertEqual(self.assist.poll_once(), "")
        self.reader.down.add("key:Space")
        self.assertEqual(self.assist.poll_once(), "up")
        self.assertEqual(self.keys(), "AAAAAA")
        self.assertEqual(self.assist.poll_once(), "")             # still held: nothing more
        self.reader.down.clear()
        self.assist.poll_once()
        self.clock.now += 0.5
        self.assertEqual(self.assist.poll_once(), "")             # not long enough yet
        self.clock.now += 1.0
        self.assertEqual(self.assist.poll_once(), "down")
        self.assertEqual(self.keys(), "AAAAAA" + "DBC")

    def test_a_quick_tap_does_not_flap_the_pips(self):
        self.reader.down.add("key:Space")
        self.assist.poll_once()
        self.reader.down.clear()
        self.assist.poll_once()
        self.clock.now += 0.5
        self.reader.down.add("key:Space")
        self.assist.poll_once()
        self.clock.now += 5
        self.reader.down.clear()
        self.assist.poll_once()
        self.assertEqual(self.keys(), "AAAAAA")                      # never reset between taps

    def test_nothing_without_hardpoints(self):
        self.state.status_flags = 0
        self.reader.down.add("key:Space")
        self.assertEqual(self.assist.poll_once(), "")
        self.assertEqual(self.keys(), "")

    def test_switched_off(self):
        self.settings.values["combat_assist.pips"] = False
        self.reader.down.add("key:Space")
        self.assertEqual(self.assist.poll_once(), "")

    def test_default_steps(self):
        self.assertEqual(DEFAULT_PIPS_UP, ["IncreaseWeaponsPower"] * 6)
        self.assertEqual(DEFAULT_PIPS_DOWN[0], "ResetPowerDistribution")


class HeatSinkTests(Base):
    def setUp(self):
        super().setUp()
        self.assist.attach()
        self.addCleanup(self.assist.detach)

    def test_heat_sink_on_overheating(self):
        self.bus.publish("Overheating", {}, "critical")
        self.assertEqual(self.keys(), "F")

    def test_heat_warning_works_too_and_has_a_cooldown(self):
        self.bus.publish("HeatWarning", {}, "critical")
        self.bus.publish("Overheating", {}, "critical")
        self.assertEqual(self.keys(), "F")

    def test_not_while_scooping_or_docked(self):
        for bit in (11, 0, 1):
            self.state.status_flags = 1 << bit
            self.clock.now += 100
            self.bus.publish("Overheating", {}, "critical")
        self.assertEqual(self.keys(), "")

    def test_works_without_hardpoints(self):
        self.state.status_flags = 0
        self.bus.publish("Overheating", {}, "critical")
        self.assertEqual(self.keys(), "F")

    def test_missing_key_is_told_once(self):
        said = []
        self.assist.speech = SimpleNamespace(say=lambda **k: said.append(k))
        self.assist.book = SimpleNamespace(lookup=lambda a: (None, "unbound"))
        self.bus.publish("Overheating", {}, "critical")
        self.clock.now += 100
        self.bus.publish("Overheating", {}, "critical")
        self.assertEqual(len(said), 1)


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.processor, self.bus, self.heard = make_processor()

    def scan(self, stage, **extra):
        entry = {"event": "ShipTargeted", "TargetLocked": True, "ScanStage": stage, "Ship": "cobramkiii",
                 "Ship_Localised": "Cobra Mk III", "PilotName_Localised": "Dave"}
        entry.update(extra)
        self.processor.handle_line(json.dumps(entry))
        return [e for e in self.heard if e.name == "ShipTargeted"][-1].data if self.heard else None

    def test_ship_name_in_a_fight(self):
        self.processor.state.status_flags = 1 << 6
        data = self.scan(0)
        self.assertEqual(data["Announce"], "ship")
        self.assertEqual(line_keys.keys_for(SimpleNamespace(name="ShipTargeted", data=data)), ["ShipTargeted_Ship"])

    def test_bounty_is_announced_once_with_commas(self):
        self.processor.state.status_flags = 1 << 6
        self.scan(0)
        data = self.scan(3, LegalStatus="Wanted", Bounty=12500)
        self.assertEqual(data["Announce"], "bounty")
        self.assertEqual(data["BountyText"], "12,500")
        self.assertEqual(self.scan(3, LegalStatus="Wanted", Bounty=12500)["Announce"], "")

    def test_quiet_without_hardpoints(self):
        self.processor.state.status_flags = 0
        self.assertEqual(self.scan(0)["Announce"], "")
        self.assertEqual(self.scan(3, LegalStatus="Clean")["Announce"], "")

    def test_wanted_without_bounty_number(self):
        data = self.scan(3, LegalStatus="Wanted")
        self.assertEqual(data["Announce"], "wanted")

    def test_new_target_is_announced_again(self):
        self.processor.state.status_flags = 1 << 6
        self.scan(0)
        data = self.scan(0, Ship_Localised="Anaconda", PilotName_Localised="Bob")
        self.assertEqual(data["Announce"], "ship")


class LinesTests(unittest.TestCase):
    def test_keys_have_lines_and_fill_in(self):
        from core import paths
        from personality.dialogue import DialogueManager
        dialogue = DialogueManager(paths.VOICEPACKS_DIR / "default", [paths.DIALOGUE_DIR / "core_lines.json"]).load()
        for key, needs in (("ShipTargeted_Ship", "{Ship}"), ("ShipTargeted_Bounty", "{BountyText}")):
            pool = dialogue.pool(key, "Neutral", True)
            self.assertTrue(pool)
            for line in pool:
                self.assertIn(needs, line.text, key)
                line.text.format(Ship="X", BountyText="1")
        for key in ("CombatAssist_HeatSink", "UnderAttack", "Bounty"):
            self.assertIsNotNone(dialogue.pick(key, "Neutral", False, False), key)


if __name__ == "__main__":
    unittest.main()


class AnalysisModeTests(Base):
    def test_pips_work_in_analysis_mode_for_mining_lasers(self):
        self.state.status_flags = 1 << 27                       # analysis mode, hardpoints in
        self.reader.down.add("key:Space")
        self.assertEqual(self.assist.poll_once(), "up")

    def test_long_mining_burst_is_topped_up_and_reset_is_slower(self):
        self.state.status_flags = 1 << 27
        self.reader.down.add("key:Space")
        self.assertEqual(self.assist.poll_once(), "up")
        self.sender.pressed.clear()
        self.clock.now += 9.0                                   # still holding the trigger: weapons are topped up again
        self.assertEqual(self.assist.poll_once(), "")
        self.assertEqual(self.keys(), "AA")
        self.reader.down.clear()
        self.assertEqual(self.assist.poll_once(), "")
        self.clock.now += 1.5                                   # hardpoints mode would reset by now; analysis waits longer
        self.assertEqual(self.assist.poll_once(), "")
        self.clock.now += 2.0
        self.assertEqual(self.assist.poll_once(), "down")

    def test_x52_trigger_stages_always_count_as_fire_one_and_two(self):
        from control import inputs
        stick = inputs.JoyDevice(index=0, vendor=0x06A3, product=0x075C, name="Saitek X52", buttons=32)
        self.reader.x52_devices = lambda: [stick]
        self.assist.book = SimpleNamespace(slots=lambda action: [], lookup=self.assist.book.lookup)     # Elite names no fire buttons at all
        specs = self.assist.fire_buttons()
        self.assertIn(inputs.joy_spec(stick, 1), specs)
        self.assertIn(inputs.joy_spec(stick, 2), specs)
        self.state.status_flags = 1 << 27                       # analysis mode
        self.reader.down.add(inputs.joy_spec(stick, 2))
        self.assertEqual(self.assist.poll_once(), "up")
        self.settings.values["combat_assist.x52_trigger"] = False
        self.assist._specs_at = -999.0
        self.assertNotIn(inputs.joy_spec(stick, 1), self.assist.fire_buttons())

    def test_hardpoints_do_not_get_the_top_up(self):
        self.reader.down.add("key:Space")
        self.assist.poll_once()
        self.sender.pressed.clear()
        self.clock.now += 20
        self.assist.poll_once()
        self.assertEqual(self.keys(), "")

    def test_not_in_analysis_mode_when_switched_off_or_in_supercruise(self):
        self.state.status_flags = 1 << 27
        self.settings.values["combat_assist.pips_analysis"] = False
        self.reader.down.add("key:Space")
        self.assertEqual(self.assist.poll_once(), "")
        self.settings.values["combat_assist.pips_analysis"] = True
        self.state.status_flags = (1 << 27) | (1 << 4)
        self.assertEqual(self.assist.poll_once(), "")
