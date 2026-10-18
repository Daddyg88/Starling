import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.event_bus import EventBus
from core.settings import Settings
from ui.settings_model import SettingsModel, microphone_choices
from ui.status import EventFeed, collect_status

MICS = lambda: [(1, "Mic A"), (2, "Mic A"), (3, "Mic B")]


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "settings.json"
        self.settings = Settings(self.path).load()
        self.model = SettingsModel(self.settings, mic_lister=MICS, pack_folder=Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_microphones_listed_once_with_default_first(self):
        labels = [l for l, _ in microphone_choices(MICS)]
        self.assertEqual(labels, ["Windows default", "Mic A", "Mic B"])

    def test_microphone_failure_still_gives_default(self):
        def boom():
            raise RuntimeError("no audio")
        self.assertEqual(microphone_choices(boom), [("Windows default", "")])

    def test_every_field_key_exists_in_settings(self):
        for f in self.model.all_fields():
            self.assertIsNotNone(self.settings.get(f.key, None) if f.kind != "text" else "", f.key)
            self.model.current_label(f) if f.kind == "choice" else None

    def test_choice_changes_setting(self):
        f = self.model.field("tts.volume")
        self.assertTrue(self.model.set_choice(f, "50%"))
        self.assertEqual(self.settings.get("tts.volume"), 50)
        self.assertEqual(self.model.current_label(f), "50%")

    def test_unknown_label_is_ignored(self):
        self.assertFalse(self.model.set_choice(self.model.field("tts.volume"), "nonsense"))

    def test_unknown_current_value_is_kept_as_custom(self):
        self.settings.set("tts.volume", 37)
        f = self.model.field("tts.volume")
        self.assertIn("Custom (37)", self.model.labels(f))
        self.assertEqual(self.model.current_label(f), "Custom (37)")

    def test_microphone_selected_and_saved(self):
        f = self.model.field("stt.microphone")
        self.model.set_choice(f, "Mic B")
        self.assertTrue(self.model.restart_needed())
        ok, _ = self.model.save()
        self.assertTrue(ok)
        self.assertEqual(Settings(self.path).load().get("stt.microphone"), "Mic B")
        self.assertFalse(self.model.dirty())

    def test_toggle_and_text(self):
        self.model.set_value(self.model.field("speech.allow_mature"), True)
        self.assertIs(self.settings.get("speech.allow_mature"), True)
        self.model.set_value(self.model.field("stt.wake_phrase"), "  ")
        self.assertEqual(self.settings.get("stt.wake_phrase"), "")        # empty = same as her name
        self.model.set_value(self.model.field("app.name"), " ")
        self.assertEqual(self.settings.get("app.name"), "Starling")
        self.model.set_value(self.model.field("stt.wake_phrase"), " Nova ")
        self.assertEqual(self.settings.get("stt.wake_phrase"), "Nova")

    def test_same_value_is_not_a_change(self):
        self.assertFalse(self.model.set_value(self.model.field("speech.enabled"), True))

    def test_revert(self):
        self.model.set_choice(self.model.field("personality.mood"), "Sarcastic (sassy)")
        self.assertTrue(self.model.dirty())
        self.model.revert()
        self.assertEqual(self.settings.get("personality.mood"), "Friendly")
        self.assertFalse(self.model.restart_needed())

    def test_changing_back_clears_restart_flag(self):
        f = self.model.field("stt.model")
        self.model.set_choice(f, "Balanced")
        self.assertTrue(self.model.restart_needed())
        self.model.set_choice(f, "Fast (smallest)")
        self.assertFalse(self.model.restart_needed())

    def test_voicepack_default_when_folder_empty(self):
        self.assertEqual(self.model.choices(self.model.field("personality.active_voicepack"))[0][1], "default")


class StatusTests(unittest.TestCase):
    def test_feed_skips_internal_and_keeps_newest_first(self):
        bus = EventBus()
        feed = EventFeed(bus, size=2)
        bus.publish("app.started", {})
        for n in ("a", "b", "c"):
            bus.publish("journal." + n, {})
            bus.publish("Docked", {"summary": n}, "normal")
        texts = [t for _, t, _ in feed.recent()]
        self.assertEqual(texts, ["c", "b"])

    def test_status_with_nothing_started(self):
        settings = Settings(Path(tempfile.gettempdir()) / "starling_none.json").load()
        app = SimpleNamespace(settings=settings, providers={}, listener=None, monitor=None, state=None)
        rows = dict((a, b) for a, b, _ in collect_status(app))
        self.assertEqual(rows["Listening"], "Off")
        self.assertEqual(rows["Voice"], "Not started")


if __name__ == "__main__":
    unittest.main()
