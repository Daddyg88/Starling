"""She looks at the left panel to find which tab is open, then walks to the tab she wants."""
import unittest
from pathlib import Path

import numpy as np

from control import panel_reader as pr
from control.macros import actions_in, parse_macro
from tests.test_macros import ALL as ALL_KEYS

TABS = 5                     # 0 = the small icon tab on the far left, 1 = Navigation, 2 = Transactions, 3 = Contacts, 4 = Target
NAV = 1                      # the macro's "tab 0" is Navigation = index 1 here
SHOTS = Path("/mnt/user-data/attachments/056a8d7e-59f4-5178-84a2-456c45d6729a")


def picture(tab, tabs=TABS, noise=True):
    """A made-up 1920x1080 screen: dark, a few small bright bits, the selected tab filled bright (the icon tab is a small square),
    list rows lower down, and the Request Docking bar in the right-hand pane when the Contacts tab is open."""
    pic = np.full((1080, 1920, 3), 12, dtype=np.uint8)
    if noise:
        pic[100:120, 1500:1510] = (255, 140, 0)                  # a small bright thing (not wide)
        pic[600:640, 300:900] = (255, 120, 0)                    # a big list row, LOWER down than the tab bar
    if tab == 0:
        pic[256:296, 256:296] = (255, 128, 0)                    # the icon tab, selected
    else:
        left = 300 + (tab - 1) * 250
        pic[255:290, left:left + 240] = (255, 128, 0)
    if tab == 3:
        pic[525:600, 898:1303] = (255, 170, 0)                   # REQUEST DOCKING
    return pic


class FindTabTests(unittest.TestCase):
    def test_finds_the_bar_and_moves_right_with_the_tab(self):
        spots = [pr.find_tab(picture(i)) for i in range(TABS)]
        self.assertTrue(all(spots))
        self.assertTrue(spots[0].get("icon"))
        for a, b in zip(spots, spots[1:]):
            self.assertGreater(b["cx"], a["cx"])
            self.assertFalse(b.get("icon"))

    def test_the_button_is_only_seen_when_it_is_there(self):
        self.assertIsNotNone(pr.find_button(picture(3)))
        for tab in (0, 1, 2, 4):
            self.assertIsNone(pr.find_button(picture(tab)), tab)

    def test_nothing_to_find(self):
        self.assertIsNone(pr.find_tab(np.full((1080, 1920, 3), 10, dtype=np.uint8)))
        self.assertIsNone(pr.find_tab(None))

    @unittest.skipUnless(SHOTS.exists(), "the commander's screenshots are only here")
    def test_real_screenshots(self):
        from PIL import Image
        def look(name):
            return np.asarray(Image.open(SHOTS / ("%s-image.png" % name)).convert("RGB"))
        spots = [pr.find_tab(look(n)) for n in ("e80dadc1", "d60ffe87", "a929ae94", "72528b22")]   # icon, Nav, Transactions, Contacts
        self.assertTrue(spots[0].get("icon"))
        xs = [spot["cx"] for spot in spots]
        self.assertEqual(xs, sorted(xs))
        self.assertIsNotNone(pr.find_button(look("86867523")))                  # the Request Docking screen
        for name in ("e80dadc1", "d60ffe87", "a929ae94", "72528b22"):
            self.assertIsNone(pr.find_button(look(name)), name)


class FakeGame:
    def __init__(self, tab, wrap=True, blind=False):
        self.tab, self.wrap, self.blind, self.presses = tab, wrap, blind, []

    def read(self):
        return None if self.blind else pr.find_tab(picture(self.tab))

    def nxt(self):
        self.presses.append("n")
        self.tab = (self.tab + 1) % TABS

    def prev(self):
        self.presses.append("p")
        self.tab = (self.tab - 1) % TABS if self.wrap else max(0, self.tab - 1)


class WalkTests(unittest.TestCase):
    def go(self, start, target, **kw):
        g = FakeGame(start, **kw)
        ok = pr.goto_tab(g.read, g.nxt, g.prev, lambda s: None, target)
        return ok, g

    def test_gets_to_contacts_from_every_starting_tab(self):
        for wrap in (True, False):
            for start in range(TABS):
                ok, g = self.go(start, 2, wrap=wrap)
                self.assertTrue(ok, (start, wrap))
                self.assertEqual(g.tab, NAV + 2, (start, wrap))

    def test_gets_to_each_target(self):
        for target in range(3):
            ok, g = self.go(3, target)
            self.assertTrue(ok)
            self.assertEqual(g.tab, NAV + target)

    def test_blind_means_false_and_no_keys(self):
        ok, g = self.go(2, 2, blind=True)
        self.assertFalse(ok)
        self.assertEqual(g.presses, [])


class MacroStepTests(unittest.TestCase):
    def test_parse_and_actions(self):
        self.assertEqual(parse_macro(["tab 2"]), [("tab", 2, 0)])
        self.assertEqual(parse_macro(["tab 0 from 2"]), [("tab", 0, 2)])
        self.assertEqual(parse_macro(["open left panel"]), [("openleft",)])
        self.assertEqual(actions_in(parse_macro(["open left panel"])), ["FocusLeftPanel", "UI_Back"])
        self.assertEqual(actions_in(parse_macro(["tab 2"])), ["CycleNextPanel", "CyclePreviousPanel"])
        for bad in ("tab x", "tab 9", "tab 0 from"):
            with self.assertRaises(ValueError):
                parse_macro([bad])


class RunnerTests(unittest.TestCase):
    def test_docking_starts_from_any_tab_when_she_can_see(self):
        from tests.test_macros import MacroTests
        for start in (0, 1, 3, 4):
            t = MacroTests()
            r = t.build()
            game = {"tab": start}
            keys = {"Key_3": 1, "Key_8": -1}                     # CycleNextPanel / CyclePreviousPanel in the test table
            real_send = t.sender.send

            def send(stroke, hold=0.0, _real=real_send, _game=game, _keys=keys):
                _game["tab"] = (_game["tab"] + _keys.get(stroke.key, 0)) % TABS
                return _real(stroke, hold=hold)
            t.sender.send = send
            r.panel_reader = lambda _g=game: picture(_g["tab"])
            r.state_provider = lambda: __import__("journal.game_state", fromlist=["GameState"]).GameState()
            r.sleep = lambda s: None
            with self.assertLogs("starling", level="INFO") as logs:
                r.run_text("request docking")
            self.assertTrue(any("went to tab 2" in line for line in logs.output), start)
            self.assertTrue(any(k.key == "Key_4" for k in t.sender.pressed), start)               # UI_Select (Key_4) was pressed: she saw the button
            self.assertFalse(any(k.key == "Key_9" for k in t.sender.pressed), start)             # and there is no UI_Up any more


class OpenLeftPanelTests(unittest.TestCase):
    """'open left panel' from every screen the game can be showing (GuiFocus from Status.json)."""

    def run_from(self, gui, closes_on_back=True):
        from tests.test_macros import MacroTests
        from journal.game_state import GameState
        t = MacroTests()
        r = t.build()
        state = GameState()
        state.status_seen = True
        state.gui_focus = gui
        r.state_provider = lambda: state

        def send(stroke, hold=0.0):
            t.sender.pressed.append(stroke)
            if stroke.key == "Key_6":                               # UI_Back
                if closes_on_back and state.gui_focus in (5, 6, 7, 8, 9, 10, 11):
                    state.gui_focus = 0
            elif stroke.key == "Key_0":                             # FocusLeftPanel: opens, or CLOSES if already open
                state.gui_focus = 0 if state.gui_focus == 2 else 2
            return None
        t.sender.pressed = []
        t.sender.send = send
        strokes = {"FocusLeftPanel": ALL_KEYS["FocusLeftPanel"][0], "UI_Back": ALL_KEYS["UI_Back"][0]}
        problem = r._open_left_panel(strokes, [], [])
        return problem, [s.key for s in t.sender.pressed], state.gui_focus

    def test_every_starting_screen(self):
        for gui, keys in ((0, ["Key_0"]), (1, ["Key_0"]), (2, []), (3, ["Key_0"]), (4, ["Key_0"]),
                          (5, ["Key_6", "Key_0"]), (6, ["Key_6", "Key_0"]), (7, ["Key_6", "Key_0"]), (9, ["Key_6", "Key_0"])):
            problem, pressed, end = self.run_from(gui)
            self.assertIsNone(problem, gui)
            self.assertEqual(pressed, keys, gui)
            self.assertEqual(end, 2, gui)                           # the panel is open at the end, never closed by accident

    def test_a_screen_that_will_not_close_stops_the_macro(self):
        problem, pressed, _ = self.run_from(6, closes_on_back=False)
        self.assertEqual(problem, "failed")
        self.assertEqual(pressed, ["Key_6"])                       # one Back, then she stops pressing keys


    def test_no_button_means_no_select_and_a_clear_report(self):
        from tests.test_macros import MacroTests
        t = MacroTests()
        r = t.build()
        no_button = picture(3)
        no_button[500:620, 880:1320] = 12                                                       # Contacts, but the button is not lit
        r.panel_reader = lambda: no_button
        r.sleep = lambda s: None
        outcome = r.run_text("request docking")[0]
        self.assertEqual(outcome.status, "no_button")
        self.assertFalse(any(k.key == "Key_4" for k in t.sender.pressed))                       # UI_Select was never pressed


def _no_button():
    pic = picture(3)
    pic[500:620, 880:1320] = 12
    return pic


class SelectRetryTests(unittest.TestCase):
    """Select is pressed again only when the panel is still open (it was ignored); the macro stops when the game closed the panel."""

    def run_docking(self, ignored_presses):
        from tests.test_macros import MacroTests
        from journal.game_state import GameState
        t = MacroTests()
        r = t.build()
        state = GameState()
        state.status_seen = True
        state.gui_focus = 2
        r.state_provider = lambda: state
        r.sleep = lambda s: None
        game = {"tab": 1, "selects": 0}
        keys = {"Key_3": 1, "Key_8": -1}                          # next / previous tab

        def send(stroke, hold=0.0):
            t.sender.pressed.append(stroke)
            if stroke.key in keys:
                game["tab"] = max(0, min(TABS - 1, game["tab"] + keys[stroke.key]))
            if stroke.key == "Key_4":                              # UI_Select
                game["selects"] += 1
                if game["selects"] > ignored_presses:
                    state.gui_focus = 0                            # the game closed the panel: the request went through
            return None
        t.sender.send = send
        r.panel_reader = lambda: picture(game["tab"])
        with self.assertLogs("starling", level="INFO"):
            r.run_text("request docking")
        return [k.key for k in t.sender.pressed]

    def test_a_press_that_works_stops_the_macro_there(self):
        keys = self.run_docking(0)
        self.assertEqual(keys.count("Key_4"), 1)
        self.assertNotIn("Key_10", keys)                           # no UI_Left, no Back pressed into the cockpit
        self.assertNotIn("Key_6", keys)

    def test_an_ignored_press_is_repeated(self):
        keys = self.run_docking(1)
        self.assertEqual(keys.count("Key_4"), 2)

    def test_cursor_jumps_to_the_list_row_so_she_goes_right_and_selects_again(self):
        """What the commander's maps showed: an ignored Select sends the cursor to the station row in the list (button dark)."""
        from tests.test_macros import MacroTests
        from journal.game_state import GameState
        for needed in (1, 2, 3, 99):                                # the game answers on this press of Select (99 = never)
            t = MacroTests()
            r = t.build()
            state = GameState()
            state.status_seen = True
            state.gui_focus = 2
            r.state_provider = lambda: state
            r.sleep = lambda s: None
            game = {"tab": 1, "selects": 0, "cursor": "button"}
            keys = {"Key_3": 1, "Key_8": -1}

            def send(stroke, hold=0.0, _g=game, _s=state, _n=needed, _k=keys):
                t.sender.pressed.append(stroke)
                if stroke.key in _k:
                    _g["tab"] = max(0, min(TABS - 1, _g["tab"] + _k[stroke.key]))
                if stroke.key == "Key_5" and _g["cursor"] == "row":            # UI_Right: back to the button
                    _g["cursor"] = "button"
                if stroke.key == "Key_4" and _g["tab"] == 3 and _g["cursor"] == "button":   # UI_Select on the button
                    _g["selects"] += 1
                    if _g["selects"] >= _n:
                        _s.gui_focus = 0                                # the request went through; the game closes the panel
                    else:
                        _g["cursor"] = "row"                            # ignored: the cursor jumps to the list row
                return None
            t.sender.send = send
            r.panel_reader = lambda _g=game: _no_button() if (_g["tab"] == 3 and _g["cursor"] == "row") else picture(_g["tab"])
            with self.assertLogs("starling", level="INFO"):
                r.run_text("request docking")
            keys_pressed = [k.key for k in t.sender.pressed]
            self.assertEqual(keys_pressed.count("Key_4"), min(needed, 3), needed)
            self.assertEqual(keys_pressed.count("Key_5"), 1 + min(needed, 3) - 1, needed)   # the macro's own Right + one per ignored Select

    def test_it_gives_up_after_three_presses(self):
        keys = self.run_docking(99)
        self.assertEqual(keys.count("Key_4"), 3)


if __name__ == "__main__":
    unittest.main()
