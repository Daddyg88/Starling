import unittest

from control.bio_voice import BioOverlayVoice
from journal.bio_predict import BioPredictor
from journal.game_state import GameState
from tests.test_bio_predict import fss, planet, run
from ui import bio_overlay as ov


class Settings:
    def __init__(self, **values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


class Formatting(unittest.TestCase):
    def test_credits(self):
        self.assertEqual(ov.short_credits(4200000), "4.2M")
        self.assertEqual(ov.short_credits(19010800), "19M")
        self.assertEqual(ov.short_credits(850000), "850K")
        self.assertEqual(ov.short_credits(0), "?")

    def test_rows_and_flags(self):
        rows = [{"body": "A 1", "count": 2, "new": 5, "value": 4200000, "known": False, "kind": "icy"},
                {"body": "A 2", "count": 1, "new": 0, "value": 1500000, "known": True}]
        lines, more = ov.overlay_rows(rows)
        self.assertEqual(lines[0]["flags"], 2)                  # never more flags than signals
        self.assertEqual(lines[0]["value"], "~4.2M")            # a guess
        self.assertEqual(lines[1]["value"], "1.5M")             # scanned: no tilde
        self.assertEqual(lines[1]["flags"], 0)
        self.assertEqual(more, "")

    def test_more(self):
        rows = [{"body": "P%d" % i, "count": 1, "new": 0, "value": 1, "known": True} for i in range(11)]
        lines, more = ov.overlay_rows(rows)
        self.assertEqual((len(lines), more), (8, "and 3 more"))


class Placement(unittest.TestCase):
    def test_bottom_left_quarter_up(self):
        x, y = ov.placement(1920, 1080, 300, 200, 3, 25)
        self.assertEqual(x, 57)
        self.assertEqual(y, 1080 - 270 - 200)

    def test_stays_on_screen(self):
        x, y = ov.placement(1000, 800, 400, 300, 95, 95)
        self.assertLessEqual(x + 400, 1000)
        self.assertGreaterEqual(y, 0)


class When(unittest.TestCase):
    def test_shows_only_planets_with_life_and_forgets(self):
        _, state = run([planet("Test A 1", k=177), fss("Test A 1", 2)])
        rows, test = ov.wanted(Settings(), state)
        self.assertEqual(len(rows), 1)
        self.assertFalse(test)
        self.assertEqual(rows[0]["count"], 2)
        self.assertGreater(rows[0]["value"], 0)
        state.bio.set_system("Elsewhere")
        self.assertEqual(ov.wanted(Settings(), state)[0], [])

    def test_switch_off_and_hidden(self):
        _, state = run([planet("Test A 1", k=177), fss("Test A 1", 1)])
        self.assertEqual(ov.wanted(Settings(**{"overlay.bio_enabled": False}), state)[0], [])
        state.bio.hidden = True
        self.assertEqual(ov.wanted(Settings(), state)[0], [])

    def test_test_mode(self):
        rows, test = ov.wanted(Settings(), GameState(), now=5.0, test_until=10.0)
        self.assertTrue(test)
        self.assertEqual(len(rows), 3)
        self.assertEqual(ov.wanted(Settings(), GameState(), now=11.0, test_until=10.0)[0], [])


class Voice(unittest.TestCase):
    def test_hide_and_show(self):
        _, state = run([planet("Test A 1", k=177), fss("Test A 1", 1)])
        voice = BioOverlayVoice(lambda: state)
        for text in ("hide the bio overlay", "Close the biology overlay.", "get rid of the exobiology box", "turn off the bio list"):
            state.bio.hidden = False
            self.assertEqual(voice.try_handle(text), "Biology overlay hidden.", text)
            self.assertTrue(state.bio.hidden)
        for text in ("show the bio overlay", "bring up the biology list please"):
            state.bio.hidden = True
            self.assertEqual(voice.try_handle(text), "Biology overlay shown.", text)
            self.assertFalse(state.bio.hidden)

    def test_ignores_everything_else(self):
        _, state = run([])
        voice = BioOverlayVoice(lambda: state)
        for text in ("hide the galaxy map", "show me the overlay", "plot a route to Colonia", "", "open the bio hatch"):
            self.assertIsNone(voice.try_handle(text), text)

    def test_hidden_clears_in_next_system(self):
        _, state = run([])
        state.bio.hidden = True
        state.bio.set_system("Elsewhere")
        self.assertFalse(state.bio.hidden)


if __name__ == "__main__":
    unittest.main()


class FakeCanvas:
    def __init__(self, *a, **k):
        self.items = []

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.items.append((name, args, kwargs))
        return call


class FakeWindow(FakeCanvas):
    def winfo_id(self):
        return 1


class FakeTk:
    Toplevel = FakeWindow
    Canvas = FakeCanvas


class FakeRoot:
    def __init__(self):
        self.jobs = []

    def after(self, ms, fn):
        self.jobs.append(fn)

    def winfo_screenwidth(self):
        return 1920

    def winfo_screenheight(self):
        return 1080


class DrawingTests(unittest.TestCase):
    """Runs the drawing code against a stand-in for tkinter (there is no screen here), to catch typing mistakes."""

    def setUp(self):
        import sys
        self._saved = sys.modules.get("tkinter")
        sys.modules["tkinter"] = FakeTk

    def tearDown(self):
        import sys
        if self._saved is None:
            sys.modules.pop("tkinter", None)
        else:
            sys.modules["tkinter"] = self._saved

    def test_draw_show_and_hide(self):
        _, state = run([planet("Test A 1", k=177), fss("Test A 1", 2)])
        root = FakeRoot()
        box = ov.BioOverlay(root, Settings(), lambda: state)
        box._update()
        names = [n for n, _, _ in box.canvas.items]
        self.assertIn("create_polygon", names)                 # a white flag
        self.assertIn("create_oval", names)                    # a planet
        self.assertEqual([n for n, _, _ in box.window.items if n == "deiconify"], ["deiconify"])
        before = len(box.canvas.items)
        box._update()                                          # nothing changed: no redraw
        self.assertEqual(len(box.canvas.items), before)
        state.bio.hidden = True
        box._update()
        self.assertIn("withdraw", [n for n, _, _ in box.window.items])

    def test_test_button(self):
        box = ov.BioOverlay(FakeRoot(), Settings(), lambda: GameState())
        box.show_test(5)
        box._update()
        self.assertIsNotNone(box.window)
        for dark in (True, False):
            for size in ("Small", "Large"):
                box._draw(*ov.overlay_rows(ov.TEST_ROWS), (3, 25, size, dark))
