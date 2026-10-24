"""Mood pictures, the Bookmarks tab, and saying bookmark names to the route plotter."""

import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.settings import DEFAULTS
from navigation.voice import slot_key, slot_name
from tests.test_commands import ControlsTestScreenTests
from tests import test_neutron
from tests.test_phase6b import make_settings
from ui import portraits
from ui.settings_model import SettingsModel


class PortraitTests(unittest.TestCase):
    def test_pictures_match_moods_and_bad_moods_use_neutral(self):
        names = {m: portraits.portrait_for(m).stem for m in portraits.MOODS}
        self.assertEqual(names, {"Infatuated": "Close", "Close": "Close", "Friendly": "Friendly", "Neutral": "Neutral",
                                 "Sarcastic": "Neutral", "Frustrated": "Neutral", "Upset": "Neutral"})

    def test_unknown_mood_is_neutral(self):
        self.assertEqual(portraits.portrait_for("Whatever").stem, "Neutral")

    def test_a_new_picture_is_picked_up_by_name(self):
        folder = Path(tempfile.mkdtemp())
        (folder / "Neutral.png").write_bytes(b"x")
        (folder / "Sarcastic.JPG".lower()).write_bytes(b"x")
        self.assertEqual(portraits.portrait_for("Sarcastic", folder).name, "sarcastic.jpg")
        self.assertEqual(portraits.portrait_for("Frustrated", folder).name, "Neutral.png")

    def test_all_shipped_pictures_open(self):
        from PIL import Image
        for mood in ("Close", "Friendly", "Neutral"):
            with Image.open(portraits.portrait_for(mood)) as picture:
                self.assertGreaterEqual(min(picture.size), 300)

    def test_fit_keeps_the_shape(self):
        self.assertEqual(portraits.fit(640, 640, 300, 380), (300, 300))
        w, h = portraits.fit(517, 640, 300, 380)
        self.assertLessEqual((w, h), (300, 380))
        self.assertAlmostEqual(w / h, 517 / 640, places=1)


class BookmarkSettings(unittest.TestCase):
    def test_eleven_boxes(self):
        page = next(p for p in SettingsModel(make_settings()).pages if p.id == "bookmarks")
        self.assertEqual([f.label for f in page.fields], ["Home", "Fleet carrier", "Squad carrier"] + ["Bookmark %d" % n for n in range(1, 11)])
        self.assertEqual(set(DEFAULTS["bookmarks"]), {"home", "fleet", "squad"} | {"b%d" % n for n in range(1, 11)})

    def test_saving_through_the_model(self):
        settings = make_settings()
        model = SettingsModel(settings)
        model.set_value(model.field("bookmarks.b3"), "  Colonia ")
        self.assertEqual(settings.get("bookmarks.b3"), "Colonia")
        self.assertTrue(model.dirty())


class SpokenBookmarks(unittest.TestCase):
    def test_slot_names(self):
        for text, key in [("home", "home"), ("my home", "home"), ("bookmark 4", "b4"), ("bookmark four", "b4"),
                          ("Bookmark Number 10", "b10"), ("book mark two", "b2"), ("bookmark 11", None), ("colonia", None)]:
            self.assertEqual(slot_key(text), key, text)
        self.assertEqual((slot_name("home"), slot_name("b7")), ("Home", "Bookmark 7"))

    def test_plot_to_a_bookmark(self):
        t = test_neutron.VoiceTests()
        t.build(bookmarks__home="Shinrarta Dezhra", bookmarks__b3="Colonia")
        t.v.try_handle("plot a neutron route to home")
        t.v.try_handle("plot a neutron route to bookmark three")
        self.assertIn(("find", "Shinrarta Dezhra"), t.spansh.asked)
        self.assertIn(("find", "Colonia"), t.spansh.asked)

    def test_empty_bookmark_is_explained(self):
        t = test_neutron.VoiceTests()
        t.build()
        t.v.try_handle("plot a neutron route to bookmark 5")
        self.assertEqual(t.keys(), ["RouteBookmarkEmpty"])
        self.assertEqual(t.narr.said[0][1]["slot"], "Bookmark 5")
        self.assertEqual([c for c in t.spansh.asked if c[0] == "route"], [])

    def test_save_this_system(self):
        for text, key in [("save this system as bookmark 3", "b3"), ("set home to here", "home"),
                          ("bookmark this system as home", "home"), ("remember this system in bookmark two", "b2"),
                          ("set my home to this system", "home")]:
            t = test_neutron.VoiceTests()
            t.build(system="Eorld Byoi KP-A c1-4")
            saved = []
            t.settings.save = lambda: saved.append(1)
            self.assertIn("Saved", t.v.try_handle(text), text)
            self.assertEqual(t.settings.get("bookmarks." + key), "Eorld Byoi KP-A c1-4", text)
            self.assertEqual((t.keys(), saved), (["RouteBookmarkSaved"], [1]), text)

    def test_save_needs_to_know_where_we_are(self):
        t = test_neutron.VoiceTests()
        t.build(system=None)
        t.v.try_handle("save this system as home")
        self.assertEqual(t.keys(), ["RouteNoLocation"])
        self.assertEqual(t.settings.get("bookmarks.home"), "")

    def test_ordinary_route_sentences_are_not_saves(self):
        t = test_neutron.VoiceTests()
        t.build()
        for text in ("set a neutron route to colonia", "plot a neutron route to home", "put the gear down"):
            t.v.try_handle(text)
        self.assertEqual(t.settings.get("bookmarks.home"), "")

    def test_lines_exist_and_format(self):
        from tests.test_phase6b import dialogue
        pool = dialogue()
        for key in ("RouteBookmarkSaved", "RouteBookmarkEmpty"):
            for mood in ("Close", "Friendly", "Neutral", "Sarcastic", "Frustrated"):
                lines = pool.pool(key, mood, False, False)
                self.assertTrue(lines, (key, mood))
                for line in lines:
                    line.text.format(slot="Home", system="Sol")


class DashboardUiTests(unittest.TestCase):
    """Builds the real dashboard code against a pretend window library."""

    def setUp(self):
        self.saved = sys.modules.get("customtkinter")
        fake = mock.MagicMock()
        fake.CTkCanvas.return_value.winfo_width.return_value = 800
        fake.CTkCanvas.return_value.winfo_height.return_value = 78
        sys.modules["customtkinter"] = fake
        self.addCleanup(lambda: sys.modules.pop("customtkinter", None) if self.saved is None
                        else sys.modules.__setitem__("customtkinter", self.saved))
        import ui.dashboard as dashboard
        importlib.reload(dashboard)
        self.dashboard = dashboard
        self.app = ControlsTestScreenTests().make()[0]

    def test_every_page_builds_including_bookmarks(self):
        d = self.dashboard.Dashboard(self.app)
        for page in ("home", "navigation", "voice", "game", "personality"):
            self.assertIn(page, d.page_frames)
            d.show(page)
        self.assertEqual(len(d._bookmark_entries), 13)

    def test_picture_follows_the_mood(self):
        d = self.dashboard.Dashboard(self.app)
        shown = []
        d._portrait_image = lambda path: shown.append(path.stem) or "img"
        for mood, picture in [("Close", "Close"), ("Friendly", "Friendly"), ("Sarcastic", "Neutral"), ("Frustrated", "Neutral")]:
            self.app.settings.set("personality.mood_mode", "fixed")
            self.app.settings.set("personality.mood", mood)
            d._update_portrait()
            self.assertEqual(shown[-1], picture, mood)
            self.assertIn(mood.upper(), d._mood_chip.configure.call_args.kwargs["text"])
        n = len(shown)
        d._update_portrait()                                  # same mood again: nothing is touched
        self.assertEqual(len(shown), n)

    def test_here_button_fills_the_current_system(self):
        from journal.game_state import GameState
        self.app.state = GameState()
        self.app.state.system = "Colonia"
        d = self.dashboard.Dashboard(self.app)
        field, entry = d._bookmark_entries["bookmarks.b2"]
        d.use_current_system(field, entry)
        self.assertEqual(self.app.settings.get("bookmarks.b2"), "Colonia")
        entry.insert.assert_called_with(0, "Colonia")

    def test_here_button_without_a_system(self):
        d = self.dashboard.Dashboard(self.app)
        field, entry = d._bookmark_entries["bookmarks.home"]
        d.use_current_system(field, entry)
        self.assertEqual(self.app.settings.get("bookmarks.home"), "")

    def test_typing_in_a_box_is_never_wiped(self):
        """The bug: a once-a-second refresh put the saved (empty) value back while you were typing or pasting."""
        d = self.dashboard.Dashboard(self.app)
        field, entry = d._bookmark_entries["bookmarks.b1"]
        entry.reset_mock()                                    # (the pretend entries are one shared object)
        entry.get.return_value = "Colonia"                    # what you have pasted so far (not committed yet)
        for _ in range(5):
            d._sync_bookmarks()
        entry.delete.assert_not_called()
        entry.insert.assert_not_called()

    def test_a_later_voice_save_still_shows(self):
        d = self.dashboard.Dashboard(self.app)
        field, entry = d._bookmark_entries["bookmarks.b1"]
        entry.reset_mock()
        entry.get.return_value = ""
        d._sync_bookmarks()
        self.app.settings.set("bookmarks.b1", "Sol")
        d._sync_bookmarks()
        d._sync_bookmarks()
        entry.insert.assert_called_once_with(0, "Sol")

    def test_menu_buttons_have_a_visible_outline(self):
        from ui import theme
        d = self.dashboard.Dashboard(self.app)
        self.assertNotEqual(theme.BORDER_GLOW, theme.SIDEBAR)
        button = d.nav_buttons["voice"]
        button.reset_mock()
        d.show("voice")
        d.show("home")
        colours = [c.kwargs.get("border_color") for c in button.configure.call_args_list]
        self.assertIn(theme.BORDER_GLOW, colours)      # a page you are not on: outlined
        self.assertIn(theme.ACCENT, colours)           # the page you are on: outlined brighter

    def test_voice_saved_bookmark_appears_in_the_box(self):
        d = self.dashboard.Dashboard(self.app)
        field, entry = d._bookmark_entries["bookmarks.b4"]
        entry.get.return_value = ""
        self.app.settings.set("bookmarks.b4", "Sol")
        d._sync_bookmarks()
        entry.insert.assert_called_with(0, "Sol")


if __name__ == "__main__":
    unittest.main()
