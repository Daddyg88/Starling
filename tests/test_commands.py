"""Phase 6 tests: keys, bindings, key pressing, phrase matching, the command runner, buttons, push-to-talk."""

import tempfile
import time
import unittest
from pathlib import Path

from control import binds, keys, sender as sender_module
from control.binds import BindingBook, Keystroke, find_binds_file, parse_binds
from control.catalog import CATALOG
from control.inputs import ButtonReader, JoyDevice, describe, parse_spec
from control.matcher import Matcher, expand, normalise
from control.ptt import PushToTalk
from control.runner import CommandRunner
from control.sender import KeySender
from core import paths
from core.event_bus import EventBus
from core.settings import Settings
from journal.game_state import GameState
from personality.dialogue import DialogueManager
from personality.voice_replies import VoiceReplies

BINDS = """<?xml version="1.0" encoding="UTF-8" ?>
<Root PresetName="Custom" MajorVersion="4" MinorVersion="0">
  <LandingGearToggle>
    <Primary Device="Keyboard" Key="Key_L" />
    <Secondary Device="{NoDevice}" Key="" />
  </LandingGearToggle>
  <GalaxyMapOpen>
    <Primary Device="Keyboard" Key="Key_M"><Modifier Device="Keyboard" Key="Key_LeftShift" /></Primary>
    <Secondary Device="{NoDevice}" Key="" />
  </GalaxyMapOpen>
  <SystemMapOpen>
    <Primary Device="231D0200" Key="Joy_5" />
    <Secondary Device="Keyboard" Key="Key_Numpad_7" />
  </SystemMapOpen>
  <DeployHardpointToggle>
    <Primary Device="231D0200" Key="Joy_1" />
    <Secondary Device="{NoDevice}" Key="" />
  </DeployHardpointToggle>
  <ToggleCargoScoop>
    <Primary Device="{NoDevice}" Key="" />
    <Secondary Device="{NoDevice}" Key="" />
  </ToggleCargoScoop>
  <CycleNextHostileTarget>
    <Primary Device="Keyboard" Key="Key_T" />
    <Secondary Device="{NoDevice}" Key="" />
  </CycleNextHostileTarget>
  <UseShieldCell>
    <Primary Device="Keyboard" Key="Key_Weird_Key" />
    <Secondary Device="{NoDevice}" Key="" />
  </UseShieldCell>
  <ThrottleAxis><Binding Device="231D0200" Key="Joy_ZAxis" /><Inverted Value="0" /></ThrottleAxis>
</Root>
"""


def make_settings(**values):
    s = Settings(Path(tempfile.gettempdir()) / "nope_commands.json").load()
    for k, v in values.items():
        s.set(k.replace("__", "."), v)
    return s


class KeyTests(unittest.TestCase):
    def test_common_keys_have_scancodes(self):
        self.assertEqual(keys.scancode_for("Key_L"), (0x26, False))
        self.assertEqual(keys.scancode_for("Key_Space"), (0x39, False))
        self.assertEqual(keys.scancode_for("Key_Numpad_0"), (0x52, False))
        self.assertEqual(keys.scancode_for("Key_LeftShift"), (0x2A, False))

    def test_grey_keys_are_extended(self):
        self.assertTrue(keys.scancode_for("Key_UpArrow")[1])
        self.assertTrue(keys.scancode_for("Key_RightAlt")[1])
        self.assertFalse(keys.scancode_for("Key_Numpad_8")[1])

    def test_case_and_prefix_do_not_matter_and_unknown_is_none(self):
        self.assertEqual(keys.scancode_for("key_l"), keys.scancode_for("Key_L"))
        self.assertIsNone(keys.scancode_for("Key_Banana"))

    def test_every_letter_digit_and_function_key_exists(self):
        for name in list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") + ["F%d" % i for i in range(1, 13)]:
            self.assertTrue(keys.is_known("Key_" + name), name)

    def test_no_two_plain_keys_share_a_scancode(self):
        seen = {}
        for name, code in keys._TABLE.items():
            if name in ("esc", "return", "equal", "leftctrl", "rightctrl", "semicolon", "quote", "backquote", "tilde",
                        "backslash", "forwardslash", "fullstop"):
                continue    # aliases of one key
            seen.setdefault(code, []).append(name)
        clashes = {c: n for c, n in seen.items() if len(n) > 1}
        self.assertEqual(clashes, {})

    def test_nice_names(self):
        self.assertEqual(keys.nice_name("Key_LeftShift"), "Left Shift")
        self.assertEqual(keys.nice_name("Key_Numpad_0"), "Numpad 0")


class BindsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "Custom.4.0.binds").write_text(BINDS, encoding="utf-8")
        (self.dir / "StartPreset.start").write_text("Custom\nCustom\nCustom\nCustom\n")
        self.book = BindingBook(self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_reads_actions_and_ignores_axes(self):
        actions = parse_binds(BINDS)
        self.assertIn("LandingGearToggle", actions)
        self.assertEqual(actions["GalaxyMapOpen"][0].modifiers, [("Keyboard", "Key_LeftShift")])
        self.assertNotIn("ThrottleAxis", actions)

    def test_bad_xml_is_a_clean_error(self):
        with self.assertRaises(ValueError):
            parse_binds("<Root><oops>")

    def test_simple_key(self):
        stroke, why = self.book.lookup("LandingGearToggle")
        self.assertEqual((stroke, why), (Keystroke("Key_L"), ""))

    def test_key_with_modifier(self):
        stroke, _ = self.book.lookup("GalaxyMapOpen")
        self.assertEqual(stroke, Keystroke("Key_M", ("Key_LeftShift",)))
        self.assertEqual(stroke.describe(), "Left Shift + M")

    def test_secondary_keyboard_key_is_used_when_primary_is_a_joystick(self):
        stroke, _ = self.book.lookup("SystemMapOpen")
        self.assertEqual(stroke.key, "Key_Numpad_7")

    def test_joystick_only_is_reported(self):
        self.assertEqual(self.book.lookup("DeployHardpointToggle"), (None, binds.JOYSTICK_ONLY))

    def test_unbound_and_missing_and_unknown_key(self):
        self.assertEqual(self.book.lookup("ToggleCargoScoop"), (None, binds.UNBOUND))
        self.assertEqual(self.book.lookup("NoSuchAction"), (None, binds.NOT_IN_FILE))
        with self.assertLogs("starling.binds", level="WARNING"):
            self.assertEqual(self.book.lookup("UseShieldCell"), (None, binds.UNKNOWN_KEY))

    def test_no_folder_means_no_file(self):
        book = BindingBook(self.dir / "missing")
        self.assertEqual(book.lookup("LandingGearToggle"), (None, binds.NO_FILE))
        self.assertIn("can't find", book.error)

    def test_changes_to_the_file_are_noticed(self):
        self.assertEqual(self.book.lookup("LandingGearToggle")[0].key, "Key_L")
        time.sleep(0.01)
        (self.dir / "Custom.4.0.binds").write_text(BINDS.replace("Key_L", "Key_G") + " ", encoding="utf-8")
        self.assertEqual(self.book.lookup("LandingGearToggle")[0].key, "Key_G")

    def test_start_preset_chooses_the_file(self):
        (self.dir / "Mine.4.0.binds").write_text(BINDS.replace("Key_L", "Key_P"), encoding="utf-8")
        (self.dir / "StartPreset.start").write_text("Mine\nMine\n")
        self.assertEqual(find_binds_file(self.dir).name, "Mine.4.0.binds")

    def test_falls_back_to_the_newest_file_for_built_in_presets(self):
        (self.dir / "StartPreset.start").write_text("KeyboardMouseOnly\n")
        self.assertEqual(find_binds_file(self.dir).name, "Custom.4.0.binds")

    def test_older_file_versions_are_found(self):
        (self.dir / "Custom.4.0.binds").unlink()
        (self.dir / "Custom.3.0.binds").write_text(BINDS, encoding="utf-8")
        self.assertEqual(find_binds_file(self.dir).name, "Custom.3.0.binds")

    def test_folder_comes_from_localappdata(self):
        folder = binds.bindings_folder({"LOCALAPPDATA": "C:\\Users\\x\\AppData\\Local"})
        self.assertTrue(str(folder).endswith("Bindings"))
        self.assertIsNone(binds.bindings_folder({}))


class FakeKeyboard:
    def __init__(self, fail_on=None):
        self.events, self.fail_on = [], fail_on

    def key_event(self, code, extended, down):
        if down and self.fail_on == len(self.events):
            raise OSError("blocked")
        self.events.append((code, extended, down))


class SenderTests(unittest.TestCase):
    def sender(self, kb=None, focused=True, **kw):
        return KeySender(keyboard=kb or FakeKeyboard(), focus_check=lambda: focused, sleep=lambda s: None, **kw)

    def test_modifier_down_key_down_key_up_modifier_up(self):
        kb = FakeKeyboard()
        self.assertEqual(self.sender(kb).send(Keystroke("Key_M", ("Key_LeftShift",))), "")
        self.assertEqual(kb.events, [(0x2A, False, True), (0x32, False, True), (0x32, False, False), (0x2A, False, False)])

    def test_nothing_is_pressed_when_the_game_is_not_in_front(self):
        kb = FakeKeyboard()
        self.assertEqual(self.sender(kb, focused=False).send(Keystroke("Key_L")), sender_module.GAME_NOT_ACTIVE)
        self.assertEqual(kb.events, [])

    def test_focus_check_can_be_switched_off(self):
        kb = FakeKeyboard()
        self.assertEqual(self.sender(kb, focused=False, require_game=False).send(Keystroke("Key_L")), "")
        self.assertEqual(len(kb.events), 2)

    def test_unknown_key_is_refused_before_pressing_anything(self):
        kb = FakeKeyboard()
        self.assertEqual(self.sender(kb).send(Keystroke("Key_Nope")), sender_module.UNKNOWN_KEY)
        self.assertEqual(kb.events, [])

    def test_keys_are_released_even_if_something_breaks(self):
        kb = FakeKeyboard(fail_on=1)       # the second key-down fails
        with self.assertLogs("starling.sender", level="ERROR"):
            result = self.sender(kb).send(Keystroke("Key_M", ("Key_LeftShift",)))
        self.assertEqual(result, sender_module.FAILED)
        self.assertEqual(kb.events, [(0x2A, False, True), (0x2A, False, False)])

    def test_without_windows_it_says_so(self):
        self.assertEqual(KeySender(sleep=lambda s: None).send(Keystroke("Key_L")), sender_module.NOT_WINDOWS)

    def test_the_windows_structures_are_the_right_size(self):
        # SendInput refuses to work if its structure is the wrong size (40 bytes on 64-bit Windows).
        import ctypes
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            self.skipTest("only checked on 64-bit")
        INPUT, UNION, KEYBDINPUT = sender_module.make_input_structures()
        self.assertEqual(ctypes.sizeof(INPUT), 40)
        self.assertEqual(ctypes.sizeof(KEYBDINPUT), 24)
        item = INPUT(type=1, u=UNION(ki=KEYBDINPUT(0, 0x26, 0x8, 0, 0)))
        self.assertEqual(item.u.ki.wScan, 0x26)


class MatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = Matcher()

    def hit(self, text):
        match = self.m.match(text)
        return (match.command.id, match.intent) if match else None

    def test_the_examples_from_the_brief(self):
        self.assertEqual(self.hit("open galaxy map"), ("galaxy_map", "on"))
        self.assertEqual(self.hit("lower landing gear"), ("gear", "on"))
        self.assertEqual(self.hit("target next hostile"), ("next_hostile", "press"))

    def test_many_ways_to_say_the_same_thing(self):
        for text in ("lower the landing gear", "drop the gear", "put the wheels down", "gear down", "deploy landing gear",
                     "could you please lower the undercarriage", "extend the landing gear", "get the gear down",
                     "Lower the landing gear, Commander!"):
            self.assertEqual(self.hit(text), ("gear", "on"), text)
        for text in ("raise the landing gear", "gear up", "retract the gear", "pull up the wheels", "stow the landing gear"):
            self.assertEqual(self.hit(text), ("gear", "off"), text)
        for text in ("open the galaxy map", "pull up the galaxy map", "show me the galaxy map", "bring up the star map",
                     "can you open the galactic map please", "galaxy map"):
            self.assertEqual(self.hit(text), ("galaxy_map", "on"), text)
        for text in ("close the galaxy map", "exit the galaxy map", "hide the star map"):
            self.assertEqual(self.hit(text), ("galaxy_map", "off"), text)

    def test_word_order_for_on_and_off(self):
        self.assertEqual(self.hit("turn the lights on"), ("lights", "on"))
        self.assertEqual(self.hit("turn off the lights"), ("lights", "off"))
        self.assertEqual(self.hit("switch the night vision on"), ("night_vision", "on"))
        self.assertEqual(self.hit("turn silent running off"), ("silent_running", "off"))

    def test_targeting(self):
        self.assertEqual(self.hit("select the next hostile"), ("next_hostile", "press"))
        self.assertEqual(self.hit("target the next enemy"), ("next_hostile", "press"))
        self.assertEqual(self.hit("target previous hostile"), ("prev_hostile", "press"))
        self.assertEqual(self.hit("target the highest threat"), ("highest_threat", "press"))
        self.assertEqual(self.hit("target next system"), ("next_route_system", "press"))
        self.assertEqual(self.hit("target wingman two"), ("wingman_2", "press"))

    def test_throttle(self):
        self.assertEqual(self.hit("set throttle to seventy five"), ("speed_75", "press"))
        self.assertEqual(self.hit("half throttle"), ("speed_50", "press"))
        self.assertEqual(self.hit("full stop"), ("speed_0", "press"))
        self.assertEqual(self.hit("full throttle"), ("speed_100", "press"))

    def test_opposites_are_never_confused(self):
        # a slightly wrong hearing may still work, but never turns into the OPPOSITE action
        self.assertEqual(self.hit("lower gear"), ("gear", "on"))
        self.assertNotEqual(self.hit("rase the landing gear"), ("gear", "on"))
        self.assertNotEqual(self.hit("next hostile"), ("prev_hostile", "press"))
        self.assertEqual(self.hit("previous hostile"), ("prev_hostile", "press"))

    def test_small_mishearings_still_work(self):
        self.assertEqual(self.hit("open the galaxy mat"), ("galaxy_map", "on"))
        self.assertEqual(self.hit("target the next hostiles ship"), ("next_hostile", "press"))
        match = self.m.match("open the galaxy mat")
        self.assertLess(match.score, 1.0)

    def test_nonsense_is_not_a_command(self):
        for text in ("", "banana sandwich", "what a lovely day", "the quick brown fox", "hello there"):
            self.assertIsNone(self.m.match(text), text)

    def test_big_actions_need_a_near_perfect_hearing(self):
        self.assertEqual(self.hit("engage supercruise"), ("supercruise", "press"))
        self.assertIsNone(self.m.match("engage supercruize now"))      # too far off for a strict command
        self.assertTrue(next(c for c in CATALOG if c.id == "hyperspace").strict)

    def test_two_commands_in_one_sentence(self):
        matches = self.m.split("lower the landing gear and open the galaxy map")
        self.assertEqual([x.command.id for x in matches], ["gear", "galaxy_map"])
        self.assertEqual(self.m.split("lower the gear and banana"), [])
        self.assertEqual(self.m.split("lower the gear"), [])

    def test_no_sentence_belongs_to_two_commands(self):
        self.assertEqual(self.m.conflicts, [])

    def test_there_are_lots_of_phrases(self):
        self.assertGreater(self.m.phrase_count(), 1000)

    def test_every_command_understands_at_least_one_phrase_and_has_text_for_each_intent(self):
        ids = set()
        for command in CATALOG:
            self.assertNotIn(command.id, ids)
            ids.add(command.id)
            self.assertTrue(command.phrases, command.id)
            for intent in command.phrases:
                self.assertTrue(command.do_text(intent), command.id)
        # every template sentence finds its own command
        for command in CATALOG:
            for intent, specs in command.phrases.items():
                for spec in specs:
                    for sentence in expand(spec)[:3]:
                        match = self.m.match(sentence)
                        self.assertIsNotNone(match, sentence)
                        self.assertEqual(match.command.id, command.id, sentence)

    def test_every_action_name_looks_like_elites(self):
        for command in CATALOG:
            if command.service:
                continue                # Void Compass overlays use no key
            self.assertRegex(command.action, r"^[A-Za-z0-9_]+$")

    def test_expand_and_normalise(self):
        self.assertEqual(sorted(expand("(open|show) [the] map")), ["open map", "open the map", "show map", "show the map"])
        self.assertEqual(normalise("Could you PLEASE lower the landing gear?!"), "lower gear")


class FakeSpeech:
    def __init__(self):
        self.said = []

    def say(self, **kw):
        self.said.append(kw)
        return True


class FakeBook:
    def __init__(self, table=None):
        self.table = table or {}
        self.path = None
        self.error = ""

    def lookup(self, action):
        return self.table.get(action, (None, binds.NOT_IN_FILE))


class FakeSender:
    def __init__(self, problem=""):
        self.pressed, self.problem, self.require_game = [], problem, True

    def send(self, stroke, hold=None):
        if self.problem:
            return self.problem
        self.pressed.append(stroke)
        return ""


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.speech = FakeSpeech()
        self.dialogue = DialogueManager(paths.VOICEPACKS_DIR / "default").load()
        self.state = GameState()
        self.book = FakeBook({
            "LandingGearToggle": (Keystroke("Key_L"), ""),
            "GalaxyMapOpen": (Keystroke("Key_M", ("Key_LeftShift",)), ""),
            "CycleNextHostileTarget": (Keystroke("Key_T"), ""),
            "DeployHardpointToggle": (None, binds.JOYSTICK_ONLY),
            "ToggleCargoScoop": (None, binds.UNBOUND),
        })
        self.sender = FakeSender()
        self.now = [100.0]
        self.events = []
        self.bus.subscribe("voice.command", self.events.append)

    def runner(self, **values):
        r = CommandRunner(self.bus, self.speech, self.dialogue, make_settings(**values), book=self.book,
                          sender=self.sender, state_provider=lambda: self.state, clock=lambda: self.now[0],
                          sleep=lambda s: None)
        r.attach()
        return r

    def summaries(self):
        return [e.data["summary"] for e in self.events]

    def hear(self, text, wake=True, command=None, ptt=False):
        self.bus.publish("voice.heard", {"text": text, "wake": wake, "ptt": ptt,
                                         "command": text if command is None else command})

    def test_lower_gear_presses_the_players_key_and_confirms(self):
        self.runner()
        self.hear("Starling lower the landing gear", command="lower the landing gear")
        self.assertEqual(self.sender.pressed, [Keystroke("Key_L")])
        self.assertIn("lowering the landing gear", self.speech.said[0]["text"].lower())

    def test_state_aware_gear_is_never_toggled_the_wrong_way(self):
        self.runner()
        self.state.status_seen, self.state.status_flags = True, 1 << 2        # gear is down
        self.hear("x", command="lower the landing gear")
        self.assertEqual(self.sender.pressed, [])
        self.assertIn("already", self.speech.said[0]["text"].lower())
        self.now[0] += 5
        self.hear("x", command="raise the landing gear")
        self.assertEqual(len(self.sender.pressed), 1)

    def test_unknown_state_just_presses(self):
        self.runner()
        self.hear("x", command="lower the landing gear")
        self.assertEqual(len(self.sender.pressed), 1)

    def test_flight_assist_uses_the_inverted_flag(self):
        r = self.runner()
        command = next(c for c in CATALOG if c.id == "flight_assist")
        self.state.status_seen, self.state.status_flags = True, 1 << 5      # bit set = assist OFF
        self.assertFalse(r.current_state(command))
        self.state.status_flags = 0
        self.assertTrue(r.current_state(command))

    def test_modifier_keys_are_passed_on(self):
        self.runner()
        self.hear("x", command="open the galaxy map")
        self.assertEqual(self.sender.pressed[0].modifiers, ("Key_LeftShift",))

    def test_joystick_only_and_unbound_are_explained_not_pressed(self):
        self.runner()
        self.hear("x", command="deploy hardpoints")
        self.hear("x", command="deploy the cargo scoop")
        self.assertEqual(self.sender.pressed, [])
        self.assertIn("joystick", self.speech.said[0]["text"].lower())
        self.assertIn("key", self.speech.said[1]["text"].lower())

    def test_game_not_in_front_is_said_out_loud(self):
        self.sender.problem = sender_module.GAME_NOT_ACTIVE
        self.runner()
        self.hear("x", command="lower the gear")
        self.assertIn("elite dangerous isn't the active window", self.summaries()[0].lower())
        self.assertEqual(len(self.speech.said), 1)

    def test_missing_binds_file_is_said_out_loud(self):
        self.book.table = {}
        self.runner()
        self.hear("x", command="target next hostile")
        self.assertIn("controls file", self.summaries()[0].lower())
        self.assertEqual(len(self.speech.said), 1)

    def test_same_command_heard_twice_quickly_presses_once(self):
        self.runner()
        self.hear("x", command="target next hostile")
        self.now[0] += 0.5
        self.hear("x", command="target next hostile")
        self.assertEqual(len(self.sender.pressed), 1)
        self.assertEqual(len(self.speech.said), 1)
        self.now[0] += 3
        self.hear("x", command="target next hostile")
        self.assertEqual(len(self.sender.pressed), 2)

    def test_two_commands_in_one_sentence(self):
        self.runner()
        self.hear("x", command="lower the landing gear and open the galaxy map")
        self.assertEqual(len(self.sender.pressed), 2)
        self.assertEqual(len(self.speech.said), 1)

    def test_without_her_name_nothing_happens(self):
        self.runner()
        self.hear("lower the landing gear", wake=False)
        self.assertEqual(self.sender.pressed, [])

    def test_push_to_talk_needs_no_name(self):
        self.runner()
        self.hear("lower the landing gear", wake=False, ptt=True)
        self.assertEqual(len(self.sender.pressed), 1)

    def test_push_to_talk_name_requirement_can_be_restored(self):
        self.runner(**{"ptt__skip_wake": False})
        self.hear("lower the landing gear", wake=False, ptt=True)
        self.assertEqual(self.sender.pressed, [])

    def test_name_alone_is_left_to_the_greeting(self):
        self.runner()
        self.hear("Starling", command="")
        self.assertEqual(self.speech.said, [])

    def test_unknown_commands_are_answered_when_addressed_but_not_for_background_chatter(self):
        self.runner(**{"stt__require_wake": False})
        self.hear("nice weather today", wake=False)
        self.assertEqual(self.speech.said, [])
        self.hear("Starling do a barrel roll please", command="do a barrel roll please")
        self.assertEqual(len(self.speech.said), 1)

    def test_commands_can_be_switched_off(self):
        self.runner(**{"commands__enabled": False})
        self.hear("x", command="lower the gear")
        self.assertEqual(self.sender.pressed, [])

    def test_a_single_command_can_be_disabled(self):
        self.runner(**{"commands__disabled": ["gear"]})
        self.hear("x", command="lower the gear")
        self.assertEqual(self.sender.pressed, [])

    def test_confirmations_can_be_turned_off_but_problems_are_still_spoken(self):
        self.runner(**{"commands__confirm": False})
        self.hear("x", command="target next hostile")
        self.assertEqual(len(self.sender.pressed), 1)
        self.assertEqual(self.speech.said, [])
        self.hear("x", command="deploy hardpoints")
        self.assertEqual(len(self.speech.said), 1)

    def test_game_focus_setting_reaches_the_sender(self):
        self.runner(**{"commands__require_game_focus": False})
        self.hear("x", command="target next hostile")
        self.assertFalse(self.sender.require_game)

    def test_every_spoken_line_fills_in_without_leftover_braces(self):
        r = self.runner(**{"speech__allow_mature": True})
        for mood in ("Friendly", "Close", "Sarcastic", "Frustrated"):
            for status in ("done", "already", "unbound", "joystick_only", "unknown_key", "no_file", "game_not_active",
                           "failed", "unknown"):
                key = __import__("control.runner", fromlist=["x"]).LINE_FOR_STATUS[status]
                for line in self.dialogue.pool(key, mood, True, False):
                    text = line.text.format(doing="Lowering the landing gear", label="the landing gear",
                                            Label="The landing gear", state="down", keys="L", count=2)
                    self.assertNotIn("{", text)
        self.assertTrue(self.dialogue.pool("CommandMulti", "", True, False))

    def test_a_command_event_is_published_for_the_dashboard(self):
        seen = []
        self.bus.subscribe("voice.command", seen.append)
        self.runner()
        self.hear("x", command="lower the gear")
        self.assertEqual(seen[0].data["status"], "done")
        self.assertEqual(seen[0].data["command"], "gear")
        self.assertEqual(seen[0].data["keys"], "L")

    def test_explain_presses_nothing(self):
        r = self.runner()
        out = r.explain("could you put the wheels down please")
        self.assertEqual(self.sender.pressed, [])
        self.assertIn("press L", out[0])
        self.assertIn("don't recognise", r.explain("fly me to the moon")[0])
        self.assertIn("joystick", r.explain("deploy weapons")[0].lower())

    def test_binding_report_counts_working_and_missing(self):
        r = self.runner()
        working, problems = r.binding_report()
        self.assertEqual(working, 3)
        self.assertTrue(problems)
        self.book.table = {}
        self.assertEqual(r.binding_report()[0], 0)

    def test_info_style_still_works_and_adds_no_banter(self):
        self.runner(**{"personality__style": "info"})
        self.hear("x", command="target next hostile")
        self.assertIn("targeting next hostile", self.speech.said[0]["text"].lower())

    def test_speech_off_means_silent_but_the_key_is_still_pressed(self):
        self.runner(**{"speech__enabled": False})
        self.hear("x", command="target next hostile")
        self.assertEqual(len(self.sender.pressed), 1)
        self.assertEqual(self.speech.said, [])


class VoiceReplyHandoverTests(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.speech = FakeSpeech()
        self.dialogue = DialogueManager(paths.VOICEPACKS_DIR / "default").load()

    def test_with_commands_active_a_request_is_not_answered_twice(self):
        VoiceReplies(self.bus, self.speech, self.dialogue, make_settings(), commands_active=True).attach()
        self.bus.publish("voice.heard", {"text": "x", "wake": True, "command": "open the galaxy map"})
        self.assertEqual(self.speech.said, [])
        self.bus.publish("voice.heard", {"text": "Starling", "wake": True, "command": ""})
        self.assertEqual(len(self.speech.said), 1)

    def test_with_commands_switched_off_she_says_she_cannot(self):
        VoiceReplies(self.bus, self.speech, self.dialogue, make_settings(**{"commands__enabled": False}),
                     commands_active=True).attach()
        self.bus.publish("voice.heard", {"text": "x", "wake": True, "command": "open the galaxy map"})
        self.assertEqual(len(self.speech.said), 1)


# ---------------------------------------------------------------------------
class FakeKeys:
    def __init__(self):
        self.down = set()

    def is_down(self, vk):
        return vk in self.down

    def all_down(self):
        return list(self.down)


class FakeJoysticks:
    def __init__(self, devices=()):
        self._devices, self.masks = list(devices), {}

    def devices(self):
        return list(self._devices)

    def buttons(self, index):
        return self.masks.get(index)


X52 = JoyDevice(0, 0x06A3, 0x075C, "Saitek X52 Flight Control System", 32)
OTHER = JoyDevice(1, 0x044F, 0xB10A, "T.16000M", 16)


class InputTests(unittest.TestCase):
    def setUp(self):
        self.kb, self.joy = FakeKeys(), FakeJoysticks([X52, OTHER])
        self.now = [0.0]
        self.reader = ButtonReader(self.kb, self.joy, clock=lambda: self.now[0])

    def test_specs_parse_and_describe(self):
        self.assertEqual(parse_spec("key:F13"), ("key", 0x7C))
        self.assertEqual(parse_spec("mouse:X1"), ("mouse", 0x05))
        self.assertEqual(parse_spec("joy:06a3:075c:7"), ("joy", "06A3:075C", 7))
        for bad in ("", "key:Banana", "joy:06A3:075C:0", "joy:06A3:075C:33", "joy:x", "mouse:Left", None):
            self.assertIsNone(parse_spec(bad), bad)
        self.assertEqual(describe("key:F13"), "Keyboard: F13")
        self.assertIn("Saitek X52", describe("joy:06A3:075C:7", [X52]))
        self.assertIn("not plugged in", describe("joy:06A3:075C:7", []))
        self.assertEqual(describe(""), "Not set")

    def test_x52_is_recognised(self):
        self.assertTrue(X52.is_x52())
        self.assertTrue(JoyDevice(0, 0x046D, 0x075C, "Game Controller", 32).is_x52())
        self.assertTrue(JoyDevice(0, 1, 2, "Saitek X-52 Pro Flight Control System", 32).is_x52())
        self.assertFalse(OTHER.is_x52())
        self.assertEqual(self.reader.x52_devices(), [X52])

    def test_keyboard_and_joystick_buttons_are_read(self):
        self.kb.down.add(0x7C)
        self.assertTrue(self.reader.is_down("key:F13"))
        self.assertFalse(self.reader.is_down("key:F14"))
        self.joy.masks[0] = 1 << 6
        self.assertTrue(self.reader.is_down("joy:06A3:075C:7"))
        self.assertFalse(self.reader.is_down("joy:06A3:075C:6"))
        self.assertFalse(self.reader.is_down("joy:FFFF:FFFF:1"))      # not plugged in

    def test_a_joystick_that_stops_answering_reads_as_not_pressed(self):
        self.joy.masks[0] = None
        self.assertFalse(self.reader.is_down("joy:06A3:075C:1"))

    def test_learn_finds_the_new_button_and_ignores_ones_already_held(self):
        self.kb.down.add(0x41)            # A is already held when learning starts
        calls = [0]

        def sleep(_):
            calls[0] += 1
            self.now[0] += 0.03
            if calls[0] == 3:
                self.joy.masks[0] = 1 << 4     # the player presses X52 button 5
        self.assertEqual(self.reader.learn(seconds=6, sleep=sleep), "joy:06A3:075C:5")

    def test_learn_gives_up(self):
        def sleep(_):
            self.now[0] += 1.0
        self.assertIsNone(self.reader.learn(seconds=3, sleep=sleep))

    def test_a_broken_joystick_service_does_not_crash(self):
        class Broken:
            def devices(self):
                raise OSError("no winmm")
        reader = ButtonReader(self.kb, Broken(), clock=lambda: self.now[0])
        with self.assertLogs("starling.inputs", level="ERROR"):
            self.assertEqual(reader.devices(), [])


class FakeReader:
    def __init__(self):
        self.down = False

    def is_down(self, spec):
        return self.down


class PttTests(unittest.TestCase):
    def setUp(self):
        self.reader = FakeReader()
        self.beeps = []
        self.now = [10.0]

    def ptt(self, **values):
        values.setdefault("ptt__button", "key:F13")
        return PushToTalk(make_settings(**values), self.reader, beep=self.beeps.append, clock=lambda: self.now[0])

    def test_off_means_always_open_and_disabled(self):
        p = self.ptt()
        self.assertFalse(p.enabled())
        self.assertTrue(p.is_open())

    def test_no_button_chosen_means_disabled(self):
        p = self.ptt(ptt__mode="hold", ptt__button="")
        self.assertFalse(p.enabled())

    def test_hold_opens_while_pressed_and_closes_on_release(self):
        p = self.ptt(ptt__mode="hold")
        p.poll_once()
        self.assertFalse(p.is_open())
        self.reader.down = True
        p.poll_once()
        self.assertTrue(p.is_open())
        self.reader.down = False
        p.poll_once()
        self.assertFalse(p.is_open())
        self.assertEqual(self.beeps, [True, False])

    def test_toggle_flips_on_each_press_and_ignores_holding(self):
        p = self.ptt(ptt__mode="toggle")
        self.reader.down = True
        p.poll_once()
        p.poll_once()                     # still held: no second flip
        self.assertTrue(p.is_open())
        self.reader.down = False
        p.poll_once()
        self.assertTrue(p.is_open())      # releasing does nothing in toggle mode
        self.now[0] += 1
        self.reader.down = True
        p.poll_once()
        self.assertFalse(p.is_open())

    def test_toggle_ignores_contact_bounce(self):
        p = self.ptt(ptt__mode="toggle")
        for pressed in (True, False, True):
            self.reader.down = pressed
            p.poll_once()
            self.now[0] += 0.05
        self.assertTrue(p.is_open())

    def test_beep_can_be_switched_off(self):
        p = self.ptt(ptt__mode="hold", ptt__beep=False)
        self.reader.down = True
        p.poll_once()
        self.assertEqual(self.beeps, [])

    def test_switching_the_mode_off_closes_the_microphone(self):
        p = self.ptt(ptt__mode="hold")
        self.reader.down = True
        p.poll_once()
        p.settings.set("ptt.mode", "off")
        p.poll_once()
        self.assertTrue(p.is_open())      # off = no gating at all
        p.settings.set("ptt.mode", "hold")
        self.reader.down = False
        p.poll_once()
        self.assertFalse(p.is_open())


class ListenerGateTests(unittest.TestCase):
    def build(self, gate):
        from tests.test_stt import FakeMic, FakeSTT
        from stt.listener import Listener
        bus = EventBus()
        heard = []
        bus.subscribe("voice.heard", heard.append)
        stt, mic = FakeSTT(text="open the galaxy map"), FakeMic([])
        return Listener(bus, stt, make_settings(), lambda: mic, gate=gate), heard, stt, mic

    def test_nothing_is_heard_while_the_button_is_not_pressed(self):
        from tests.test_stt import loud, quiet, wait_for
        gate = type("G", (), {"enabled": lambda s: True, "is_open": lambda s: False})()
        listener, heard, stt, mic = self.build(gate)
        listener.start()
        try:
            for f in quiet(45) + loud(20) + quiet(40):
                mic.frames.put(f)
            time.sleep(0.8)
        finally:
            listener.stop()
        self.assertEqual(stt.heard_audio, [])

    def test_letting_go_of_the_button_finishes_the_sentence_and_marks_it_ptt(self):
        from tests.test_stt import loud, quiet, wait_for

        class Gate:
            open = True

            def enabled(self):
                return True

            def is_open(self):
                return self.open
        gate = Gate()
        listener, heard, stt, mic = self.build(gate)
        listener.start()
        try:
            for f in quiet(45) + loud(20):             # speaking, button still held, no pause yet
                mic.frames.put(f)
            time.sleep(0.6)
            gate.open = False                           # button released mid-sentence
            mic.frames.put(quiet(1)[0])
            self.assertTrue(wait_for(lambda: heard))
        finally:
            listener.stop()
        self.assertTrue(heard[0].data["ptt"])
        self.assertEqual(heard[0].data["command"], "open the galaxy map")   # no name needed with push-to-talk

    def test_without_push_to_talk_nothing_changes(self):
        from tests.test_stt import loud, quiet, wait_for
        listener, heard, stt, mic = self.build(None)
        listener.start()
        try:
            for f in quiet(45) + loud(20) + quiet(40):
                mic.frames.put(f)
            self.assertTrue(wait_for(lambda: heard))
        finally:
            listener.stop()
        self.assertFalse(heard[0].data["ptt"])


class DetectorExtrasTests(unittest.TestCase):
    def test_flush_returns_the_sentence_so_far_or_nothing_for_noise(self):
        from stt.vad import UtteranceDetector
        from tests.test_stt import loud, quiet
        d = UtteranceDetector()
        for f in quiet(45) + loud(20):
            d.feed(f)
        self.assertIsNotNone(d.flush())
        self.assertIsNone(d.flush())               # nothing left
        for f in quiet(45) + loud(3):
            d.feed(f)
        self.assertIsNone(d.flush())               # too short: a click, not speech


class ControlsPageTests(unittest.TestCase):
    def test_the_controls_page_exists_and_every_field_has_a_default(self):
        from ui.settings_model import SettingsModel
        s = make_settings()
        model = SettingsModel(s)
        page = next(p for p in model.pages if p.id == "controls")
        for field in page.fields:
            s.get(field.key)       # does not raise
            self.assertIsNotNone(s.get(field.key, None), field.key) if field.kind != "text" else None
        model.set_choice(model.field("ptt.mode"), "Hold the button while I talk")
        self.assertEqual(s.get("ptt.mode"), "hold")

    def test_the_status_page_reports_push_to_talk(self):
        from ui.status import collect_status

        class App:
            providers, listener, monitor, state, mood = {}, None, None, None, None
            ptt = buttons = None
            settings = make_settings(ptt__mode="hold")
        rows = dict((a, b) for a, b, _c in collect_status(App))
        self.assertIn("No button", rows["Push-to-talk"])


class StatusFlagsTests(unittest.TestCase):
    def test_status_reader_records_the_raw_flags_for_voice_commands(self):
        from tests.helpers import make_processor
        from journal.status_reader import StatusReader
        processor, bus, heard = make_processor()
        reader = StatusReader(None, processor)
        reader.handle_status({"Flags": (1 << 2) | (1 << 4), "Flags2": 0}, baseline_only=True)
        self.assertTrue(processor.state.status_seen)
        self.assertEqual(processor.state.status_flags & (1 << 2), 1 << 2)


if __name__ == "__main__":
    unittest.main()


class FakeApp:
    """Just enough of App for the dashboard and the controls test."""

    def __init__(self, runner, reader):
        self.settings = make_settings()
        self.bus = EventBus()
        self.providers, self.listener, self.monitor, self.state, self.mood = {}, None, None, None, None
        self.ptt, self.speech = None, None
        self.buttons = reader
        self._runner, self._reader = runner, reader

    def ensure_commands(self):
        return self._runner

    def ensure_buttons(self):
        return self._reader


class ControlsTestScreenTests(unittest.TestCase):
    def make(self):
        kb, joy = FakeKeys(), FakeJoysticks([X52])
        reader = ButtonReader(kb, joy, clock=time.monotonic)
        book = FakeBook({"LandingGearToggle": (Keystroke("Key_L"), "")})
        runner = CommandRunner(EventBus(), None, None, make_settings(), book=book, sender=FakeSender(), sleep=lambda s: None)
        return FakeApp(runner, reader), kb, joy

    def test_the_report_shows_bindings_joysticks_pressed_buttons_and_sentences(self):
        from control.controls_test import run_controls_test
        app, kb, joy = self.make()
        lines, answers = [], iter(["lower the landing gear", ""])
        pressed = [False]

        def sleep(_):
            if not pressed[0]:
                pressed[0] = True
                joy.masks[0] = 1 << 6

        code = run_controls_test(app, reader=app._reader, seconds=0.2, out=lines.append,
                                 ask=lambda _p: next(answers), sleep=sleep)
        text = "\n".join(lines)
        self.assertEqual(code, 0)
        self.assertIn("X52 HOTAS", text)
        self.assertIn("joy:06A3:075C:7", text)
        self.assertIn("press L", text)
        self.assertIn("voice commands have a keyboard key", text)


class DashboardSmokeTests(unittest.TestCase):
    """Builds the real dashboard code against a pretend window library, then presses the Controls buttons."""

    def setUp(self):
        from unittest import mock
        self.mock = mock
        import sys
        self.saved = sys.modules.get("customtkinter")
        fake = mock.MagicMock()
        fake.CTkCanvas.return_value.winfo_width.return_value = 800
        fake.CTkCanvas.return_value.winfo_height.return_value = 70
        sys.modules["customtkinter"] = fake

        def restore():
            if self.saved is None:
                sys.modules.pop("customtkinter", None)
            else:
                sys.modules["customtkinter"] = self.saved
        self.addCleanup(restore)

    def test_controls_page_builds_and_its_buttons_work(self):
        import importlib
        import ui.dashboard as dashboard
        importlib.reload(dashboard)
        app, kb, joy = ControlsTestScreenTests().make()
        d = dashboard.Dashboard(app)
        self.assertIn("game", d.page_frames)
        d.try_entry.get.return_value = "put the wheels down"
        d.try_command()
        self.assertIn("press L", d.try_result.configure.call_args.kwargs["text"])
        d.check_keys()
        self.assertIn("1 commands have a keyboard key", d.try_result.configure.call_args.kwargs["text"])
        d.scan_joysticks()
        self.assertIn("X52", d.try_result.configure.call_args.kwargs["text"])
        d._learned("joy:06A3:075C:5", app._reader)
        self.assertEqual(app.settings.get("ptt.button"), "joy:06A3:075C:5")
        self.assertIn("Saitek X52", d.try_result.configure.call_args.kwargs["text"])
        d._learned(None, app._reader)
        self.assertIn("Nothing was pressed", d.try_result.configure.call_args.kwargs["text"])
