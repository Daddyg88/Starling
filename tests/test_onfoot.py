import unittest
from types import SimpleNamespace

from control import catalog
from control.auto_shields import AutoShields, weapon_in_hand
from control.matcher import Matcher
from control.onfoot import _load_emotes


class FakeSettings:
    def __init__(self, on=True):
        self.on = on

    def get(self, key, default=None):
        return self.on if key == "onfoot.auto_shields" else default


class FakeBook:
    def __init__(self, stroke="C"):
        self.stroke = stroke

    def lookup(self, action):
        assert action == "HumanoidToggleShieldsButton"
        return (self.stroke, "") if self.stroke else (None, "UNBOUND")


class FakeSender:
    def __init__(self):
        self.sent = []

    def send(self, stroke, hold=None):
        self.sent.append(stroke)
        return None


def foot(weapon="", health=1.0, on=True):
    return SimpleNamespace(status_flags2=1 if on else 0, selected_weapon=weapon, health=health)


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.m = Matcher(catalog.CATALOG)

    def test_phrases(self):
        for said, wanted in (("wave", "foot_emote_wave"), ("do a clap", "foot_emote_clap"), ("next grenade type", "foot_grenade_next"),
                             ("select EMP grenades", "foot_grenade_emp"), ("use a battery", "foot_battery"),
                             ("use a health pack", "foot_health"), ("torch", "foot_torch"), ("suit shields", "foot_shields"),
                             ("helmet night vision", "foot_night_vision"), ("equip the energy link", "foot_recharge_tool"),
                             ("crouch", "foot_crouch"), ("tool mode", "foot_tool_mode")):
            result = self.m.match(said)
            self.assertIsNotNone(result, said)
            self.assertEqual(result.command.id, wanted, said)

    def test_ship_night_vision_is_untouched(self):
        self.assertEqual(self.m.match("night vision").command.id, "night_vision")

    def test_every_action_is_humanoid(self):
        for command in catalog.CATALOG:
            if command.id.startswith("foot_"):
                self.assertIn("Humanoid", command.action)

    def test_emote_file_is_valid(self):
        emotes = _load_emotes()
        self.assertIn("wave", emotes)
        self.assertTrue(all(1 <= v <= 8 for v in emotes.values()))


class ShieldTests(unittest.TestCase):
    def make(self, on=True, stroke="C"):
        self.sender = FakeSender()
        self.clock = [0.0]
        return AutoShields(FakeSettings(on), FakeBook(stroke), self.sender, clock=lambda: self.clock[0])

    def test_weapon_names(self):
        self.assertTrue(weapon_in_hand("$humanoid_rifle_name;"))
        for name in ("", None, "$humanoid_fists_name;", "Energy Link"):
            self.assertFalse(weapon_in_hand(name))

    def test_drawing_a_weapon_raises_once(self):
        a = self.make()
        a.check(foot(""))
        a.check(foot("rifle"))
        a.check(foot("rifle"))
        self.assertEqual(self.sender.sent, ["C"])

    def test_holster_and_draw_again(self):
        a = self.make()
        a.check(foot(""))
        a.check(foot("rifle"))
        a.check(foot(""))
        self.clock[0] = 20
        a.check(foot("rifle"))
        self.assertEqual(len(self.sender.sent), 2)

    def test_damage_raises(self):
        a = self.make()
        a.check(foot("", 1.0))
        a.check(foot("", 0.8))
        self.assertEqual(self.sender.sent, ["C"])

    def test_already_holding_a_weapon_at_start_does_nothing(self):
        a = self.make()
        a.check(foot("rifle"))
        a.check(foot("rifle"))
        self.assertEqual(self.sender.sent, [])

    def test_off_by_default_and_when_off(self):
        a = self.make(on=False)
        a.check(foot(""))
        a.check(foot("rifle"))
        self.assertEqual(self.sender.sent, [])

    def test_not_on_foot_and_no_key(self):
        a = self.make()
        a.check(foot("", on=False))
        a.check(foot("rifle", on=False))
        self.assertEqual(self.sender.sent, [])
        b = self.make(stroke=None)
        b.check(foot(""))
        b.check(foot("rifle"))
        self.assertEqual(b.last_result, "unbound")

    def test_cooldown_after_damage_burst(self):
        a = self.make()
        a.check(foot("", 1.0))
        a.check(foot("", 0.8))
        a.check(foot("", 0.6))
        self.assertEqual(len(self.sender.sent), 1)


if __name__ == "__main__":
    unittest.main()


class PageTests(unittest.TestCase):
    def test_on_foot_has_its_own_page(self):
        from ui.settings_model import build_pages
        pages = {p.id: p for p in build_pages()}
        self.assertIn("onfoot", pages)
        self.assertEqual([f.key for f in pages["onfoot"].fields], ["onfoot.auto_shields"])
        self.assertNotIn("onfoot.auto_shields", [f.key for f in pages["combat"].fields])

    def test_updates_install_by_themselves_by_default(self):
        from core.settings import DEFAULTS
        self.assertFalse(DEFAULTS["updates"]["ask"])


class HcsBindsTests(unittest.TestCase):
    """The HCS controls file puts on-foot actions on RightAlt + Apps + a key; the Apps key used to be unknown."""

    def test_apps_key_is_known(self):
        from control import keys
        self.assertTrue(keys.is_known("Key_Apps"))
        self.assertEqual(keys.scancode_for("Key_Apps"), (0x5D, True))

    def test_hcs_chord_is_usable(self):
        import tempfile
        from pathlib import Path
        from control import binds
        folder = Path(tempfile.mkdtemp())
        (folder / "T.4.0.binds").write_text(
            '<Root><HumanoidHealthPack><Primary Device="{NoDevice}" Key="" />'
            '<Secondary Device="Keyboard" Key="Key_Q"><Modifier Device="Keyboard" Key="Key_RightAlt" />'
            '<Modifier Device="Keyboard" Key="Key_Apps" /></Secondary></HumanoidHealthPack></Root>')
        book = binds.BindingBook(folder=folder, finder=lambda f: Path(f) / "T.4.0.binds")
        stroke, why = book.lookup("HumanoidHealthPack")
        self.assertEqual((stroke.key, stroke.modifiers, why), ("Key_Q", ("Key_RightAlt", "Key_Apps"), ""))


class OnFootPresetTests(unittest.TestCase):
    """The on-foot keys can live in a different preset file from the ship's (StartPreset.start names several)."""

    def make(self, foot_bound=True):
        import tempfile
        from pathlib import Path
        from control import binds
        folder = Path(tempfile.mkdtemp())
        (folder / "StartPreset.start").write_text("HCS Custom\nHCS Custom\nMCUSTOM\nHCS Custom\n")
        (folder / "HCS Custom.4.2.binds").write_text(
            '<Root><LandingGearToggle><Primary Device="Keyboard" Key="Key_L" /><Secondary Device="{NoDevice}" Key="" /></LandingGearToggle>'
            '<HumanoidEmoteSlot2><Primary Device="{NoDevice}" Key="" /><Secondary Device="{NoDevice}" Key="" /></HumanoidEmoteSlot2></Root>')
        (folder / "MCUSTOM.4.2.binds").write_text(
            '<Root><HumanoidEmoteSlot2><Primary Device="Keyboard" Key="Key_N"><Modifier Device="Keyboard" Key="Key_T" /></Primary>'
            '<Secondary Device="{NoDevice}" Key="" /></HumanoidEmoteSlot2>'
            '<LandingGearToggle><Primary Device="Keyboard" Key="Key_K" /><Secondary Device="{NoDevice}" Key="" /></LandingGearToggle></Root>')
        return binds.BindingBook(folder=folder)

    def test_foot_keys_come_from_the_foot_preset_and_ship_keys_from_the_ship_preset(self):
        book = self.make()
        stroke, _ = book.lookup("HumanoidEmoteSlot2")
        self.assertEqual((stroke.key, stroke.modifiers), ("Key_N", ("Key_T",)))
        self.assertEqual(book.lookup("LandingGearToggle")[0].key, "Key_L")
        self.assertEqual(book.foot_path.name, "MCUSTOM.4.2.binds")
