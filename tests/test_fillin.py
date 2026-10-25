"""The missing-keys helper must NEVER change a key the player already set."""
import tempfile
import unittest
from pathlib import Path

from control import binds, fillin

FILE = (
    '<?xml version="1.0" encoding="UTF-8" ?>\r\n<Root PresetName="T" MajorVersion="4" MinorVersion="2">\r\n'
    '\t<HumanoidPing>\r\n\t\t<Primary Device="{NoDevice}" Key="" />\r\n\t\t<Secondary Device="{NoDevice}" Key="" />\r\n\t</HumanoidPing>\r\n'
    '\t<HumanoidEmoteSlot2>\r\n\t\t<Primary Device="{NoDevice}" Key="" />\r\n\t\t<Secondary Device="Keyboard" Key="Key_Z">\r\n'
    '\t\t\t<Modifier Device="Keyboard" Key="Key_RightAlt" />\r\n\t\t</Secondary>\r\n\t</HumanoidEmoteSlot2>\r\n'
    '\t<HumanoidCrouchButton>\r\n\t\t<Primary Device="Keyboard" Key="Key_Numpad_0" />\r\n\t\t<Secondary Device="{NoDevice}" Key="" />\r\n\t</HumanoidCrouchButton>\r\n'
    '\t<HumanoidJumpButton>\r\n\t\t<Primary Device="SaitekX52" Key="Joy_5" />\r\n\t\t<Secondary Device="{NoDevice}" Key="" />\r\n\t</HumanoidJumpButton>\r\n'
    '\t<HumanoidTorch>\r\n\t\t<Primary Device="{NoDevice}" Key="" />\r\n\t\t<Secondary Device="{NoDevice}" Key="" />\r\n\t</HumanoidTorch>\r\n'
    '</Root>\r\n')


def gap(path, action="HumanoidPing", label="Ping"):
    return fillin.Gap(action, label, path, [])


class FillTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "MCUSTOM.4.2.binds"
        self.path.write_bytes(FILE.encode("utf-8"))

    def actions(self):
        return binds.parse_binds(self.path.read_text(encoding="utf-8"))

    def test_only_the_chosen_empty_action_changes_and_the_rest_is_byte_for_byte(self):
        done, error = fillin.apply_choices({"HumanoidPing": "Key_Numpad_1"}, [gap(self.path)])
        self.assertEqual(error, "")
        new = self.path.read_bytes().decode("utf-8")
        self.assertEqual(new, FILE.replace('<HumanoidPing>\r\n\t\t<Primary Device="{NoDevice}" Key="" />',
                                           '<HumanoidPing>\r\n\t\t<Primary Device="Keyboard" Key="Key_Numpad_1" />'))
        self.assertTrue(any("Ping is now" in d for d in done))

    def test_a_backup_is_made_first_with_the_old_content(self):
        fillin.apply_choices({"HumanoidPing": "Key_Numpad_1"}, [gap(self.path)])
        backups = [p for p in self.dir.iterdir() if fillin.BACKUP_WORD in p.name]
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes().decode("utf-8"), FILE)
        self.assertFalse(backups[0].name.endswith(".binds"))          # Elite must not list it as a preset

    def test_an_action_that_already_has_a_key_is_never_touched(self):
        for action in ("HumanoidCrouchButton", "HumanoidJumpButton", "HumanoidEmoteSlot2"):
            done, error = fillin.apply_choices({action: "Key_Numpad_5"}, [gap(self.path, action, action)])
            self.assertEqual(done, [])
            self.assertIn("did not touch", error)
            self.assertEqual(self.path.read_bytes().decode("utf-8"), FILE)

    def test_a_key_in_use_is_refused(self):
        done, error = fillin.apply_choices({"HumanoidPing": "Key_Numpad_0"}, [gap(self.path)])     # crouch uses it
        self.assertEqual(done, [])
        self.assertEqual(self.path.read_bytes().decode("utf-8"), FILE)
        done, error = fillin.apply_choices({"HumanoidPing": "Key_RightAlt"}, [gap(self.path)])      # used as a shift key
        self.assertEqual(done, [])

    def test_two_actions_cannot_get_the_same_key(self):
        done, error = fillin.apply_choices({"HumanoidPing": "Key_Numpad_2", "HumanoidTorch": "Key_Numpad_2"},
                                           [gap(self.path), gap(self.path, "HumanoidTorch", "Torch")])
        acts = self.actions()
        keyed = [a for a in ("HumanoidPing", "HumanoidTorch") if acts[a][0].key == "Key_Numpad_2"]
        self.assertEqual(len(keyed), 1)
        self.assertIn("already used", error)

    def test_nothing_chosen_writes_nothing(self):
        done, error = fillin.apply_choices({}, [gap(self.path)])
        self.assertEqual((done, error), ([], ""))
        self.assertEqual([p for p in self.dir.iterdir() if fillin.BACKUP_WORD in p.name], [])

    def test_offered_keys_are_never_in_use_and_unpressable_ones_are_skipped(self):
        offered = fillin.free_keys(self.actions(), "HumanoidPing")
        self.assertTrue(offered)
        self.assertNotIn("Key_Numpad_0", offered)
        self.assertNotIn("Key_RightAlt", offered)
        self.assertLessEqual(len(offered), fillin.MAX_OFFERED)

    def test_a_key_used_in_another_view_is_still_offered(self):
        actions = binds.parse_binds(FILE.replace("HumanoidCrouchButton", "YawLeftButton"))     # now a ship key
        self.assertIn("Key_Numpad_0", fillin.free_keys(actions, "HumanoidPing"))

    def test_only_fully_empty_actions_count(self):
        acts = self.actions()
        self.assertTrue(fillin.is_empty_action(acts["HumanoidPing"]))
        self.assertFalse(fillin.is_empty_action(acts["HumanoidEmoteSlot2"]))
        self.assertFalse(fillin.is_empty_action(acts["HumanoidJumpButton"]))

    def test_an_odd_file_layout_is_left_alone(self):
        odd = FILE.replace('<Primary Device="{NoDevice}" Key="" />\r\n\t\t<Secondary Device="{NoDevice}" Key="" />\r\n\t</HumanoidPing>',
                           '<Primary Device="{NoDevice}" Key="" ></Primary>\r\n\t\t<Secondary Device="{NoDevice}" Key="" />\r\n\t</HumanoidPing>')
        self.path.write_bytes(odd.encode("utf-8"))
        done, error = fillin.apply_choices({"HumanoidPing": "Key_Numpad_1"}, [gap(self.path)])
        self.assertEqual(done, [])
        self.assertEqual(self.path.read_bytes().decode("utf-8"), odd)

    def test_find_gaps_lists_only_unbound_actions_and_uses_the_right_file(self):
        class Book:
            overlays = {"onfoot": None}
            path = None

            def __init__(self, p):
                self.path = p
                self.overlays = {"onfoot": p}

        class Runner:
            def __init__(self, p):
                self.book = Book(p)

            def missing_actions(self):
                return [("Ping", "HumanoidPing"), ("Jump", "HumanoidJumpButton"), ("Torch", "HumanoidTorch")]

        gaps = fillin.find_gaps(Runner(self.path))
        self.assertEqual([g.action for g in gaps], ["HumanoidPing", "HumanoidTorch"])      # joystick-bound Jump is not ours
        self.assertTrue(all(g.path == self.path and g.options for g in gaps))


if __name__ == "__main__":
    unittest.main()
