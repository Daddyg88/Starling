"""The role (bottom) panel: reading it from the commander's five screenshots, and deploying the Nomad / fighter / SRV / disembarking."""
import unittest
from pathlib import Path

import numpy as np

from control import role_reader, role_walk

FOLDER = Path("/mnt/user-data/attachments/056a8d7e-59f4-5178-84a2-456c45d6729a")
FILES = {"launch0": "ed056453", "launch1": "f9cfbf77", "srv0": "3abd3f09", "srv1": "51e512c3", "suit": "3c27df87",
         "list_suit": "f48970d6", "list_launch": "137b6f48", "list_srv": "0cb58856",
         "srv_list2": "4d789816", "srv_right": "52ca5d9a", "srv_down": "ae51e407"}      # the last three: the cursor is in the TAB LIST
HAVE = all((FOLDER / ("%s-image.png" % name)).exists() for name in FILES.values())
_cache = {}


def shot(name):
    if name not in _cache:
        from PIL import Image
        _cache[name] = np.asarray(Image.open(FOLDER / ("%s-image.png" % FILES[name])).convert("RGB"))
    return _cache[name]


@unittest.skipUnless(HAVE, "the commander's role-panel screenshots are only here")
class RealPictureTests(unittest.TestCase):
    def test_tabs(self):
        for name, tab in (("launch0", 1), ("launch1", 1), ("srv0", 2), ("srv1", 2), ("suit", 0)):
            self.assertEqual(role_reader.selected_tab(shot(name)), tab, name)

    def test_lit_button_rows(self):
        for name, row in (("launch0", 0), ("launch1", 1), ("srv0", 0), ("srv1", 1), ("suit", 1)):
            self.assertEqual(role_reader.lit_button(shot(name))["row"], row, name)

    def test_grey_cannot_deploy_buttons(self):
        self.assertEqual([b["row"] for b in role_reader.grey_buttons(shot("srv0"))], [1])     # the Scarab: ship in motion
        self.assertEqual([b["row"] for b in role_reader.grey_buttons(shot("srv1"))], [0])     # the Rhino: too close to the planet
        self.assertEqual(role_reader.grey_buttons(shot("launch0")), [])

    def test_tab_list_state_the_selected_tab_is_bright_amber_and_no_button_is_lit(self):
        for name, tab in (("list_suit", 0), ("list_launch", 1), ("list_srv", 2)):
            self.assertEqual(role_reader.selected_tab(shot(name)), tab, name)
            self.assertIsNone(role_reader.lit_button(shot(name)), name)
        self.assertEqual([b["row"] for b in role_reader.grey_buttons(shot("list_launch"))], [0, 1])   # both: too close to the planet
        self.assertEqual([b["row"] for b in role_reader.grey_buttons(shot("list_srv"))], [0])          # the Rhino only

    def test_the_cursor_on_a_greyed_out_button_is_light_grey_and_down_lights_the_next(self):
        right, down, before = shot("srv_right"), shot("srv_down"), shot("srv_list2")
        self.assertIsNone(role_reader.lit_button(right))
        self.assertEqual(role_reader.focus_button(right)["row"], 0)
        self.assertEqual(role_reader.lit_button(down)["row"], 1)
        self.assertIsNone(role_reader.focus_button(down))
        self.assertIsNone(role_reader.focus_button(before))             # tab list: nothing has the cursor
        self.assertIsNone(role_reader.lit_button(before))
        for name in ("launch0", "srv0", "list_launch", "list_srv"):
            self.assertIsNone(role_reader.focus_button(shot(name)), name)

    def test_both_rows_have_a_vessel(self):
        for name in ("launch0", "launch1", "srv0", "srv1"):
            self.assertEqual((role_reader.row_occupied(shot(name), 0), role_reader.row_occupied(shot(name), 1)), (True, True), name)

    def test_an_empty_slot_is_seen_as_empty(self):
        picture = shot("launch0").copy()
        h, w = picture.shape[:2]
        picture[int(0.385 * h):int(0.545 * h), int(w / 2 - 0.343 * h):int(w / 2 - 0.102 * h)] = (30, 5, 0)   # wipe the Nomad picture
        self.assertFalse(role_reader.row_occupied(picture, 0))
        self.assertTrue(role_reader.row_occupied(picture, 1))

    def test_other_screen_sizes(self):
        from PIL import Image
        for size in ((2560, 1440), (3840, 2160), (1280, 720)):
            picture = np.asarray(Image.fromarray(shot("srv0")).resize(size))
            self.assertEqual(role_reader.selected_tab(picture), 2, size)
            self.assertEqual(role_reader.lit_button(picture)["row"], 0, size)
            self.assertEqual(len(role_reader.grey_buttons(picture)), 1, size)


@unittest.skipUnless(HAVE, "the commander's role-panel screenshots are only here")
class SettleTests(unittest.TestCase):
    """The log showed one quick Down press racing on to the last tab, and a blurred look in between: she steps ONE key at a time and
    only trusts a look that two reads agree on."""

    def test_a_tab_list_that_runs_past_is_walked_back_one_step_at_a_time(self):
        game = FakeGame(tab=0)
        original = game.press
        presses = []

        def racing(name):                                # the first Down runs on past the tab she wanted (as in the log)
            presses.append(name)
            if name == "CycleNextPanel" and len(presses) == 1:
                game.tab = 2
            else:
                original(name)
        read = lambda: role_walk.read_all(game.picture())
        self.assertEqual(role_walk.go_to_tab(read, racing, lambda s: None, 1), "ok")
        self.assertEqual(game.tab, 1)
        self.assertEqual(presses, ["CycleNextPanel", "CyclePreviousPanel"])

    def test_a_blurred_look_is_not_an_answer(self):
        game = FakeGame(tab=1)
        blurry = [None, None]                            # two reads where nothing is clear, then the real picture
        real = lambda: role_walk.read_all(game.picture())

        def read():
            if blurry:
                blurry.pop()
                seen = real()
                seen["tab"] = None
                return seen
            return real()
        self.assertEqual(role_walk.go_to_tab(read, game.press, lambda s: None, 1), "ok")
        self.assertEqual(game.keys, [])

    def test_tab_keys_that_go_the_other_way_are_swapped(self):
        game = FakeGame(tab=1, reversed_keys=True)
        read = lambda: role_walk.read_all(game.picture())
        self.assertEqual(role_walk.go_to_tab(read, game.press, lambda s: None, 2), "ok")
        self.assertEqual(game.tab, 2)

    def test_a_two_tab_jump_presses_both_keys_then_looks_once(self):
        game = FakeGame(tab=0)
        looks = []

        def read():
            looks.append(1)
            return role_walk.read_all(game.picture())
        self.assertEqual(role_walk.go_to_tab(read, game.press, lambda s: None, 2), "ok")
        self.assertEqual(game.keys, ["CycleNextPanel", "CycleNextPanel"])
        self.assertLessEqual(len(looks), 4)                  # the first settled look and one more: the careful walk needs 6 or more

    def test_a_quick_jump_that_overshoots_is_walked_back_carefully(self):
        game = FakeGame(tab=0)
        original = game.press
        count = []

        def racing(name):                                    # the second key runs on one more tab (to the crew tab, drawn as the suit here)
            count.append(name)
            original(name)
            if len(count) == 2:
                game.tab = 1
        read = lambda: role_walk.read_all(game.picture())
        self.assertEqual(role_walk.go_to_tab(read, racing, lambda s: None, 2), "ok")
        self.assertEqual(game.tab, 2)

    def test_row_two_steps_in_and_goes_down_at_once(self):
        game = FakeGame(tab=1)
        read = lambda: role_walk.read_all(game.picture())
        self.assertEqual(role_walk.pick(read, game.press, lambda s: None, 1, 1)[0], "ok")
        self.assertEqual(game.keys, ["UI_Right", "UI_Down", "UI_Select"])

    def test_up_and_down_are_never_used_for_tabs(self):
        game = FakeGame(tab=0)
        read = lambda: role_walk.read_all(game.picture())
        role_walk.go_to_tab(read, game.press, lambda s: None, 2)
        self.assertEqual(set(game.keys), {"CycleNextPanel"})

    def test_all_grey_page_is_blocked_after_stepping_in(self):
        picture = shot("list_launch")
        keys = []
        result = role_walk.pick(lambda: role_walk.read_all(picture), keys.append, lambda s: None, 1, 0)
        self.assertEqual(result[0], "blocked")
        self.assertEqual(keys, ["UI_Right"])             # she stepped in to look, and never pressed Select


class ReasonTests(unittest.TestCase):
    def test_reasons(self):
        self.assertEqual(role_walk.blocked_reason("scarab", 0, None), "landed")
        self.assertEqual(role_walk.blocked_reason("disembark", 2, None), "other")        # landed: something else is wrong
        self.assertEqual(role_walk.blocked_reason("rhino", 0, 200), "high30")
        self.assertEqual(role_walk.blocked_reason("rhino", 0, None), "landed")
        self.assertEqual(role_walk.blocked_reason("slf", 0, 120), "slf_low")
        self.assertEqual(role_walk.blocked_reason("slf", 0, None), "other")
        self.assertEqual(role_walk.blocked_reason("nomad", 0, None), "other")
        self.assertEqual(role_walk.blocked_reason("nomad", 2, None), "close")         # landed: "too close to planet"
        self.assertEqual(role_walk.blocked_reason("slf", 2, None), "close")


class FakeGame:
    """The role panel as a little game: tabs (Up/Down in the tab list), rows (Up/Down in a page), Right / Left, Select."""
    def __init__(self, tab=0, in_page=False, lit_in_list=False, stuck_rows=(), empty=(), closes_on=None, reversed_keys=False, grey_top=False):
        self.tab, self.in_page, self.row = tab, in_page, 0
        self.closes_on, self.closed, self.reversed_keys = closes_on, False, reversed_keys
        self.grey_top = grey_top
        self.lit_in_list, self.stuck_rows, self.empty = lit_in_list, stuck_rows, empty
        self.keys, self.selected = [], None

    def press(self, name):
        self.keys.append(name)
        if name == self.closes_on:
            self.closed = True                       # a key that shuts the panel (as UI_Up did in the log)
            return
        if name in ("CycleNextPanel", "CyclePreviousPanel"):
            step = 1 if name == "CycleNextPanel" else -1
            if self.reversed_keys:
                step = -step
            self.tab = max(0, min(3, self.tab + step))
        elif name == "UI_Right":
            self.in_page = True
        elif name == "UI_Left":
            self.in_page = False
        elif name in ("UI_Up", "UI_Down"):
            step = 1 if name == "UI_Down" else -1
            if self.in_page and self.tab in (1, 2):
                new = max(0, min(1, self.row + step))
                if new not in self.stuck_rows:
                    self.row = new
            # in the tab list Up / Down do NOT change tab (the log: they ran on, or closed the panel)
        elif name == "UI_Select":
            self.selected = (self.tab, self.row)

    def picture(self):
        if self.tab == 1:
            base = "launch%d" % self.row
        elif self.tab == 2:
            base = "srv%d" % self.row
        else:
            base = "suit"
        picture = shot(base).copy()
        if self.grey_top and self.tab in (1, 2) and self.row == 0 and self.in_page:
            picture = shot("srv_right").copy()           # the Rhino is greyed out and the cursor sits on it (drawn light grey)
        if not self.in_page and not self.lit_in_list:
            red, green = picture[..., 0].astype(int), picture[..., 1].astype(int)
            lit = (red >= 185) & (green >= 105) & (green <= 170) & (picture[..., 2] <= 45)
            picture[lit] = (49, 15, 0)               # the cursor is not on a button: nothing is lit
        h, w = picture.shape[:2]
        for row in self.empty:
            y0, y1 = int(role_reader.ROW_ART_Y[row][0] * h), int(role_reader.ROW_ART_Y[row][1] * h)
            picture[y0:y1, int(w / 2 - 0.343 * h):int(w / 2 - 0.102 * h)] = (30, 5, 0)
        return picture


@unittest.skipUnless(HAVE, "the commander's role-panel screenshots are only here")
class WalkTests(unittest.TestCase):
    def walk(self, game, target, row, tab=None):
        read = lambda: role_walk.read_all(game.picture())
        wait = lambda s: None
        got = role_walk.go_to_tab(read, game.press, wait, target)
        if got != "ok" or row == "none":
            return got, None
        return got, role_walk.pick(read, game.press, wait, target, row)[0]

    def test_launch_bay_top_row_from_the_suit_tab(self):
        for lit_in_list in (False, True):
            game = FakeGame(tab=0, lit_in_list=lit_in_list)
            self.assertEqual(self.walk(game, 1, 0), ("ok", "ok"), lit_in_list)
            self.assertEqual(game.selected, (1, 0))

    def test_second_row_from_the_srv_tab(self):
        game = FakeGame(tab=2)
        self.assertEqual(self.walk(game, 1, 1), ("ok", "ok"))
        self.assertEqual(game.selected, (1, 1))

    def test_a_walk_that_is_already_there_presses_no_tab_keys(self):
        game = FakeGame(tab=2)
        self.walk(game, 2, 0)
        self.assertNotIn("UI_Up", game.keys[:1])
        self.assertEqual(game.selected, (2, 0))

    def test_suit_tab_disembark(self):
        game = FakeGame(tab=2)
        self.assertEqual(self.walk(game, 0, None), ("ok", "ok"))
        self.assertEqual(game.selected[0], 0)

    def test_an_empty_slot_is_reported_and_nothing_is_pressed(self):
        game = FakeGame(tab=1, empty=(0,))
        self.assertEqual(self.walk(game, 1, 0), ("ok", "missing"))
        self.assertIsNone(game.selected)

    def test_a_button_that_will_not_light_is_blocked(self):
        game = FakeGame(tab=2, stuck_rows=(0,))
        game.row = 1                                 # the cursor sits on the Scarab, the Rhino row is greyed out
        self.assertEqual(self.walk(game, 2, 0), ("ok", "blocked"))
        self.assertIsNone(game.selected)

    def test_unreadable_screen(self):
        self.assertEqual(role_walk.go_to_tab(lambda: None, lambda n: None, lambda s: None, 1), "unreadable")


@unittest.skipUnless(HAVE, "the commander's role-panel screenshots are only here")
class CommandTests(unittest.TestCase):
    """Whole commands through the runner: 'deploy the nomad', 'launch the fighter', 'deploy the scarab', 'disembark'."""

    def run_command(self, phrase, game, readable=True, flags=0, altitude=None, shift_down=False):
        from journal.game_state import GameState
        from tests.test_macros import MacroTests
        t = MacroTests()
        r = t.build()
        if shift_down:
            from control.binds import Keystroke
            r.book.table = dict(r.book.table)                       # a copy: the table is shared by other tests
            r.book.table["UI_Down"] = (Keystroke("Key_RightShift"), "")
        state = GameState()
        state.status_seen = True
        state.gui_focus = 0
        state.status_flags = flags
        state.altitude = altitude
        r.state_provider = lambda: state
        r.sleep = lambda s: None
        names = {"Key_2": None, "Key_3": "CycleNextPanel", "Key_8": "CyclePreviousPanel", "Key_4": "UI_Select", "Key_5": "UI_Right", "Key_6": "UI_Back", "Key_7": "UI_Down",
                 "Key_9": "UI_Up", "Key_10": "UI_Left"}

        def send(stroke, hold=0.0):
            t.sender.pressed.append(stroke)
            if stroke.key == "Key_2":                              # FocusRadarPanel
                state.gui_focus = 0 if state.gui_focus == 4 else 4
            elif names.get(stroke.key):
                game.press(names[stroke.key])
                if names[stroke.key] == "UI_Select":
                    state.gui_focus = 0                            # the panel goes away after a deploy
                if names[stroke.key] == "UI_Back" or game.closed:
                    state.gui_focus = 0
            return None
        t.sender.send = send
        r.panel_reader = (lambda: game.picture()) if readable else (lambda: None)
        with self.assertLogs("starling", level="INFO"):
            outcome = r.run_text(phrase)[0]
        return outcome, game

    def test_nomad(self):
        outcome, game = self.run_command("deploy the nomad", FakeGame(tab=0))
        self.assertEqual(outcome.status, "done")
        self.assertEqual(game.selected, (1, 0))

    def test_fighter(self):
        for phrase in ("launch the fighter", "deploy the slf", "launch the taipan"):
            outcome, game = self.run_command(phrase, FakeGame(tab=2))
            self.assertEqual(outcome.status, "done", phrase)
            self.assertEqual(game.selected, (1, 1), phrase)

    def test_srv_variants(self):
        outcome, game = self.run_command("deploy the rhino", FakeGame(tab=0))
        self.assertEqual((outcome.status, game.selected), ("done", (2, 0)))
        outcome, game = self.run_command("deploy the scorpion", FakeGame(tab=0))
        self.assertEqual((outcome.status, game.selected), ("done", (2, 1)))
        outcome, game = self.run_command("deploy the srv", FakeGame(tab=1))
        self.assertEqual((outcome.status, game.selected), ("done", (2, 0)))

    def test_disembark(self):
        for phrase in ("disembark", "get out of the ship"):
            outcome, game = self.run_command(phrase, FakeGame(tab=1), flags=2)
            self.assertEqual((outcome.status, game.selected[0]), ("done", 0), phrase)

    def test_no_nomad_on_board(self):
        outcome, game = self.run_command("deploy the nomad", FakeGame(tab=1, empty=(0,)))
        self.assertEqual(outcome.status, "no_nomad")
        self.assertIsNone(game.selected)
        self.assertIn("UI_Back", game.keys + ["UI_Back"])

    def test_no_fighter_on_board(self):
        outcome, game = self.run_command("launch the fighter", FakeGame(tab=1, empty=(1,)))
        self.assertEqual(outcome.status, "no_slf")
        self.assertIsNone(game.selected)

    def test_scarab_when_not_landed_says_why(self):
        game = FakeGame(tab=2, stuck_rows=(1,))
        outcome, game = self.run_command("deploy the scarab", game, flags=0)
        self.assertEqual(outcome.status, "cannot_landed")
        self.assertIsNone(game.selected)

    def test_fighter_too_low_says_why(self):
        game = FakeGame(tab=1, stuck_rows=(1,))
        outcome, game = self.run_command("launch the fighter", game, altitude=120.0)
        self.assertEqual(outcome.status, "cannot_slf_low")

    def test_the_top_button_greyed_out_so_down_reaches_the_second(self):
        """The log: Rhino greyed (too close to planet), Scarab deployable below it: 'deploy SRV' must press Down and then Select."""
        game = FakeGame(tab=0, grey_top=True)
        outcome, game = self.run_command("deploy the srv", game)
        self.assertEqual((outcome.status, game.selected), ("done", (2, 1)))
        self.assertIn("UI_Down", game.keys)

    def test_the_rhino_greyed_out_is_blocked_without_pressing_down(self):
        game = FakeGame(tab=0, grey_top=True)
        outcome, game = self.run_command("deploy the rhino", game)
        self.assertEqual(outcome.status, "cannot_landed")
        self.assertNotIn("UI_Down", game.keys)
        self.assertIsNone(game.selected)

    def test_heard_wrong_words_still_match(self):
        for phrase in ("deployed rhino", "deployed there rhino", "deployed the srv"):
            outcome, game = self.run_command(phrase, FakeGame(tab=0))
            self.assertNotEqual(outcome.status, "unknown", phrase)

    def test_a_bare_shift_key_for_ui_down_is_never_pressed(self):
        """The commander's UI Down keyboard key is Right Shift: pressed alone it moved the tab. She tells him instead of pressing it."""
        game = FakeGame(tab=0, grey_top=True)
        outcome, game = self.run_command("deploy the srv", game, shift_down=True)
        self.assertEqual(outcome.status, "cannot_key")
        self.assertNotIn("UI_Down", game.keys)
        self.assertIsNone(game.selected)

    def test_the_panel_closing_stops_every_key(self):
        """The log: a key shut the panel and the keys after it went into the cockpit. Now nothing more is pressed once it is closed."""
        game = FakeGame(tab=0, closes_on="CycleNextPanel")
        outcome, game = self.run_command("deploy the nomad", game)
        self.assertEqual(outcome.status, "no_button")
        self.assertEqual(game.keys, ["CycleNextPanel"])
        self.assertIsNone(game.selected)

    def test_unreadable_screen_presses_no_menu_keys(self):
        outcome, game = self.run_command("deploy the nomad", FakeGame(tab=0), readable=False)
        self.assertEqual(outcome.status, "no_button")
        self.assertEqual([k for k in game.keys if k != "UI_Back"], [])        # only the tidy-up Back

    def test_every_status_has_a_voice_line_and_an_explanation(self):
        from control.runner import LINE_FOR_STATUS
        import json
        pools = json.load(open(Path(__file__).resolve().parent.parent / "voicepacks/default/commands.json"))
        for status in ("no_nomad", "no_slf", "no_srv", "cannot_landed", "cannot_high30", "cannot_slf_low", "cannot_other"):
            self.assertIn(LINE_FOR_STATUS[status], pools)


if __name__ == "__main__":
    unittest.main()
