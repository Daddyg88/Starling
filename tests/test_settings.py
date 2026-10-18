import json
import tempfile
import unittest
from pathlib import Path

from core.settings import DEFAULTS, Settings, load_event_config


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.dir = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def test_missing_file_gives_defaults(self):
        s = Settings(self.dir / "settings.json").load()
        self.assertEqual(s.get("tts.provider"), DEFAULTS["tts"]["provider"])

    def test_partial_file_is_filled_with_defaults(self):
        path = self.dir / "settings.json"
        path.write_text(json.dumps({"tts": {"volume": 40}}), encoding="utf-8")
        s = Settings(path).load()
        self.assertEqual(s.get("tts.volume"), 40)
        self.assertEqual(s.get("tts.provider"), "kokoro")

    def test_save_and_reload(self):
        path = self.dir / "settings.json"
        s = Settings(path).load()
        s.set("tts.volume", 55)
        s.save()
        self.assertEqual(Settings(path).load().get("tts.volume"), 55)

    def test_damaged_file_is_backed_up_not_lost(self):
        path = self.dir / "settings.json"
        path.write_text("{ this is not json", encoding="utf-8")
        with self.assertLogs("starling.settings", level="ERROR"):
            s = Settings(path).load()
        self.assertEqual(s.get("tts.provider"), "kokoro")
        self.assertTrue((self.dir / "settings.json.bad").exists())

    def test_critical_events_cannot_be_disabled(self):
        path = self.dir / "events.json"
        path.write_text(json.dumps({"events": {
            "HullDamage": {"enabled": False, "priority": "critical"},
            "Scan": {"enabled": False, "priority": "low"},
        }}), encoding="utf-8")
        events = load_event_config(path)
        self.assertTrue(events["HullDamage"]["enabled"])
        self.assertFalse(events["Scan"]["enabled"])

    def test_shipped_events_file_is_valid(self):
        events = load_event_config()
        self.assertIn("LowFuel", events)
        self.assertEqual(events["LowFuel"]["priority"], "critical")


if __name__ == "__main__":
    unittest.main()
