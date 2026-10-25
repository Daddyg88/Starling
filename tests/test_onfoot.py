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
    """The on-foot keys can live in a different preset file from the ship's."""

    FILLER = "".join('<HumanoidFiller%d><Primary Device="Keyboard" Key="Key_J" /><Secondary Device="{NoDevice}" Key="" /></HumanoidFiller%d>' % (i, i)
                     for i in range(12))

    def make(self, start_lines="HCS Custom\nHCS Custom\nMCUSTOM\nHCS Custom\n", foot_name="MCUSTOM.4.2.binds", preset=""):
        import tempfile
        from pathlib import Path
        from control import binds
        binds.PRESET_NAMES["onfoot"] = preset
        self.addCleanup(binds.PRESET_NAMES.__setitem__, "onfoot", "")
        folder = Path(tempfile.mkdtemp())
        if start_lines is not None:
            (folder / "StartPreset.start").write_text(start_lines)
        (folder / "HCS Custom.4.2.binds").write_text(
            '<Root><LandingGearToggle><Primary Device="Keyboard" Key="Key_L" /><Secondary Device="{NoDevice}" Key="" /></LandingGearToggle>'
            '<HumanoidEmoteSlot2><Primary Device="{NoDevice}" Key="" /><Secondary Device="{NoDevice}" Key="" /></HumanoidEmoteSlot2></Root>')
        (folder / foot_name).write_text(
            '<Root><HumanoidEmoteSlot2><Primary Device="Keyboard" Key="Key_N"><Modifier Device="Keyboard" Key="Key_T" /></Primary>'
            '<Secondary Device="{NoDevice}" Key="" /></HumanoidEmoteSlot2>' + self.FILLER +
            '<LandingGearToggle><Primary Device="Keyboard" Key="Key_K" /><Secondary Device="{NoDevice}" Key="" /></LandingGearToggle></Root>')
        return binds.BindingBook(folder=folder, finder=lambda f: Path(f) / "HCS Custom.4.2.binds")

    def check(self, book, name="MCUSTOM.4.2.binds"):
        stroke, _ = book.lookup("HumanoidEmoteSlot2")
        self.assertEqual((stroke.key, stroke.modifiers), ("Key_N", ("Key_T",)))
        self.assertEqual(book.lookup("LandingGearToggle")[0].key, "Key_L")      # ship keys stay on the ship preset
        self.assertEqual(book.foot_path.name, name)

    def test_named_in_start_preset(self):
        self.check(self.make())

    def test_name_typed_on_the_on_foot_page(self):
        self.check(self.make(start_lines="HCS Custom\n", preset="MCUSTOM"))

    def test_found_by_looking_through_the_folder(self):
        self.check(self.make(start_lines=None, foot_name="Whatever.4.0.binds"), name="Whatever.4.0.binds")

    def test_no_foot_file_means_the_ship_file_is_used(self):
        from pathlib import Path
        import tempfile
        from control import binds
        folder = Path(tempfile.mkdtemp())
        (folder / "HCS Custom.4.2.binds").write_text('<Root><HumanoidJumpButton><Primary Device="Keyboard" Key="Key_Space" /></HumanoidJumpButton></Root>')
        book = binds.BindingBook(folder=folder, finder=lambda f: Path(f) / "HCS Custom.4.2.binds")
        self.assertEqual(book.lookup("HumanoidJumpButton")[0].key, "Key_Space")
        self.assertIsNone(book.foot_path)

    def test_describe_folder_lists_files(self):
        from control import binds
        book = self.make()
        text = "\n".join(binds.describe_folder(book.folder))
        self.assertIn("MCUSTOM.4.2.binds", text)
        self.assertIn("StartPreset.start names", text)


class KeybindsPageTests(unittest.TestCase):
    def test_keybinds_page_comes_first_and_has_a_box_per_group(self):
        from ui.settings_model import build_pages
        pages = build_pages()
        self.assertEqual(pages[0].id, "keybinds")
        self.assertEqual([f.key for f in pages[0].fields],
                         ["keybinds.ship", "onfoot.preset", "keybinds.srv", "keybinds.fighter", "keybinds.multicrew"])

    def test_names_reach_the_bindings_code(self):
        from control import binds
        settings = FakeSettings()
        settings.get = lambda key, default=None: {"keybinds.ship": " HCS Custom ", "onfoot.preset": "MCUSTOM"}.get(key, default)
        binds.set_preset_names(settings)
        self.addCleanup(lambda: [binds.PRESET_NAMES.__setitem__(k, "") for k in binds.PRESET_NAMES])
        self.assertEqual((binds.PRESET_NAMES["ship"], binds.PRESET_NAMES["onfoot"], binds.PRESET_NAMES["srv"]), ("HCS Custom", "MCUSTOM", ""))

    def test_typed_srv_preset_is_used_for_srv_keys_only(self):
        import tempfile
        from pathlib import Path
        from control import binds
        binds.PRESET_NAMES["srv"] = "Rover"
        self.addCleanup(binds.PRESET_NAMES.__setitem__, "srv", "")
        folder = Path(tempfile.mkdtemp())
        (folder / "Ship.4.0.binds").write_text('<Root><LandingGearToggle><Primary Device="Keyboard" Key="Key_L" /></LandingGearToggle>'
                                               '<IncreaseSpeed_Buggy><Primary Device="Keyboard" Key="Key_P" /></IncreaseSpeed_Buggy></Root>')
        (folder / "Rover.4.0.binds").write_text('<Root><LandingGearToggle><Primary Device="Keyboard" Key="Key_K" /></LandingGearToggle>'
                                                '<IncreaseSpeed_Buggy><Primary Device="Keyboard" Key="Key_O" /></IncreaseSpeed_Buggy></Root>')
        book = binds.BindingBook(folder=folder, finder=lambda f: Path(f) / "Ship.4.0.binds", foot_finder=None)
        self.assertEqual(book.lookup("IncreaseSpeed_Buggy")[0].key, "Key_O")
        self.assertEqual(book.lookup("LandingGearToggle")[0].key, "Key_L")


class PresetDropDownTests(unittest.TestCase):
    def test_every_preset_in_the_folder_is_listed_once(self):
        import tempfile
        from pathlib import Path
        from ui.settings_model import preset_choices
        folder = Path(tempfile.mkdtemp())
        for name in ("HCS Custom.4.2.binds", "HCS Custom.4.0.binds", "MCUSTOM.4.2.binds", "Old Setup.3.0.binds", "notes.txt", "Custom.binds"):
            (folder / name).write_text("<Root/>")
        found = preset_choices(folder)
        self.assertEqual(found[0], ("Automatic (she works it out)", ""))
        self.assertEqual([v for _l, v in found[1:]], ["Custom", "HCS Custom", "MCUSTOM", "Old Setup"])

    def test_missing_folder_still_gives_automatic(self):
        from pathlib import Path
        from ui.settings_model import preset_choices
        self.assertEqual(preset_choices(Path("/nowhere/at/all")), [("Automatic (she works it out)", "")])

    def test_keybinds_boxes_are_drop_downs_and_keep_a_saved_name(self):
        from ui.settings_model import build_pages
        pages = build_pages()
        self.assertTrue(all(f.kind == "choice" for f in pages[0].fields))
        from pathlib import Path
        from core.settings import Settings
        from ui.settings_model import SettingsModel
        settings = Settings(Path("nope.json")).load()
        settings.set("onfoot.preset", "MCUSTOM")
        model = SettingsModel(settings)
        field = model.field("onfoot.preset")
        self.assertIn("MCUSTOM", [value for _label, value in model.choices(field)])      # a saved name is never lost
