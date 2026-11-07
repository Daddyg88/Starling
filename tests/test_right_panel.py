"""The right-hand panel (Home icon | Modules | Fire Groups | Ship | Inventory | Storage | Status): she finds the open tab on the
commander's real screenshots and walks to any tab from any other."""
import unittest
from pathlib import Path

import numpy as np

from control import panel_reader as pr

SHOTS = Path("/mnt/user-data/attachments/056a8d7e-59f4-5178-84a2-456c45d6729a")
FILES = ["cfed8be3", "09e7a28c", "7f614198", "6fe30dd5", "73499e7c", "1281e45a", "ca0424ea"]   # home, modules, fire, ship, inventory, storage, status
NAMES = ["home", "modules", "fire groups", "ship", "inventory", "storage", "status"]
HAVE = all((SHOTS / ("%s-image.png" % f)).exists() for f in FILES)
_cache = {}


def shot(index):
    if index not in _cache:
        from PIL import Image
        _cache[index] = np.asarray(Image.open(SHOTS / ("%s-image.png" % FILES[index])).convert("RGB"))
    return _cache[index]


@unittest.skipUnless(HAVE, "the commander's right-panel screenshots are only here")
class RealRightPanelTests(unittest.TestCase):
    def test_each_screenshot_is_read_as_its_own_tab(self):
        spots = [pr.find_tab(shot(i)) for i in range(7)]
        self.assertTrue(spots[0].get("icon"), "home is the small icon tab")
        xs = [spot["cx"] for spot in spots]
        self.assertEqual(xs, sorted(xs), dict(zip(NAMES, xs)))                  # left to right, like the panel
        for spot in spots[1:]:
            self.assertFalse(spot.get("icon"))
            self.assertLess(abs(spot["y"] - spots[0]["y"]), 0.03)

    def test_walk_from_every_tab_to_every_tab(self):
        spots = {}

        def read_for(game):
            if game["tab"] not in spots:
                spots[game["tab"]] = pr.find_tab(shot(game["tab"]))
            return spots[game["tab"]]
        for start in range(7):
            for target in range(6):                                            # Modules .. Status
                game = {"tab": start, "presses": 0}

                def nxt(g=game):
                    g["tab"] = min(6, g["tab"] + 1)
                    g["presses"] += 1

                def prev(g=game):
                    g["tab"] = max(0, g["tab"] - 1)
                    g["presses"] += 1
                ok = pr.goto_tab(lambda g=game: read_for(g), nxt, prev, lambda s: None, target, memory={}, last_index=7)
                self.assertTrue(ok, (NAMES[start], NAMES[target + 1]))
                self.assertEqual(game["tab"], target + 1, (NAMES[start], NAMES[target + 1]))

    def test_second_walk_uses_exactly_the_keys_needed(self):
        spots = {}
        memory = {}

        def walk(start, target):
            game = {"tab": start, "presses": 0}

            def read(g=game):
                if g["tab"] not in spots:
                    spots[g["tab"]] = pr.find_tab(shot(g["tab"]))
                return spots[g["tab"]]

            def nxt(g=game):
                g["tab"] = min(6, g["tab"] + 1)
                g["presses"] += 1

            def prev(g=game):
                g["tab"] = max(0, g["tab"] - 1)
                g["presses"] += 1
            self.assertTrue(pr.goto_tab(read, nxt, prev, lambda s: None, target, memory=memory, last_index=7))
            return game
        walk(1, 5)                                                              # learns every tab on the way
        for start, target in ((6, 0), (2, 4), (4, 1)):
            game = walk(start, target)
            self.assertEqual(game["presses"], abs(target + 1 - start), (start, target))


@unittest.skipUnless(HAVE, "the commander's right-panel screenshots are only here")
class RightPanelCommandTests(unittest.TestCase):
    """'open the inventory' end to end: Focus Right Panel (from the cockpit), then Next/Previous Tab until the inventory is lit."""

    def run_command(self, phrase, start_tab, gui=0, readable=True):
        from journal.game_state import GameState
        from tests.test_macros import MacroTests
        t = MacroTests()
        r = t.build()
        state = GameState()
        state.status_seen = True
        state.gui_focus = gui
        r.state_provider = lambda: state
        r.sleep = lambda s: None
        game = {"tab": start_tab}

        def send(stroke, hold=0.0):
            t.sender.pressed.append(stroke)
            if stroke.key == "Key_1":                              # FocusRightPanel
                state.gui_focus = 0 if state.gui_focus == 1 else 1
            if stroke.key == "Key_3":                              # CycleNextPanel
                game["tab"] = min(6, game["tab"] + 1)
            if stroke.key == "Key_8":                              # CyclePreviousPanel
                game["tab"] = max(0, game["tab"] - 1)
            return None
        t.sender.send = send
        r.panel_reader = (lambda: shot(game["tab"])) if readable else (lambda: None)
        with self.assertLogs("starling", level="INFO"):
            outcome = r.run_text(phrase)[0]
        return outcome, game, [k.key for k in t.sender.pressed]

    def test_inventory_from_the_cockpit(self):
        for start in (0, 1, 6):
            outcome, game, keys = self.run_command("open the inventory", start)
            self.assertEqual(outcome.status, "done", start)
            self.assertEqual(game["tab"], 4, start)                # the Inventory screenshot
            self.assertEqual(keys[0], "Key_1")                     # Focus Right Panel first

    def test_already_open_panel_is_not_closed_by_pressing_focus_again(self):
        outcome, game, keys = self.run_command("open storage", 2, gui=1)
        self.assertEqual(outcome.status, "done")
        self.assertNotIn("Key_1", keys)
        self.assertEqual(game["tab"], 5)

    def test_when_she_cannot_see_she_presses_no_tab_keys(self):
        outcome, game, keys = self.run_command("open status tab", 3, readable=False)
        self.assertEqual(outcome.status, "no_button")
        self.assertNotIn("Key_3", keys)
        self.assertNotIn("Key_8", keys)


class ClosePanelsTests(unittest.TestCase):
    def close(self, gui, depth):
        """depth = how many Back presses the game needs before the panel is gone (the cursor can be deep inside it)."""
        from journal.game_state import GameState
        from tests.test_macros import MacroTests
        t = MacroTests()
        r = t.build()
        state = GameState()
        state.status_seen = True
        state.gui_focus = gui
        r.state_provider = lambda: state
        r.sleep = lambda s: None
        left = {"n": depth}

        def send(stroke, hold=0.0):
            t.sender.pressed.append(stroke)
            if stroke.key == "Key_6" and state.gui_focus in (1, 2, 3, 4):      # UI_Back
                left["n"] -= 1
                if left["n"] <= 0:
                    state.gui_focus = 0
            return None
        t.sender.send = send
        outcome = r.run_text("close the panel")[0]
        return outcome, [k.key for k in t.sender.pressed]

    def test_presses_back_until_the_panel_is_gone(self):
        for depth in (1, 2, 3):
            for gui in (1, 2):
                outcome, keys = self.close(gui, depth)
                self.assertEqual(outcome.status, "done")
                self.assertEqual(keys.count("Key_6"), depth, (gui, depth))

    def test_nothing_to_close_means_no_keys(self):
        outcome, keys = self.close(0, 1)
        self.assertEqual(keys, [])

    def test_a_map_is_left_alone(self):
        outcome, keys = self.close(6, 1)                                         # galaxy map: not a panel
        self.assertEqual(keys, [])

    def test_stops_after_four_presses(self):
        outcome, keys = self.close(2, 99)
        self.assertEqual(keys.count("Key_6"), 4)


if __name__ == "__main__":
    unittest.main()
