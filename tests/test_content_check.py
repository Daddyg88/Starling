"""The safety nets: dialogue checker, data backups and upgrades, and the diagnostics zip."""
import json
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path

from core import backup, diagnostics
from tools import check_dialogue


class DialogueCheckerTests(unittest.TestCase):
    def test_her_real_lines_have_no_serious_problems(self):
        serious, _notes = check_dialogue.check()
        self.assertEqual(serious, [])

    def test_the_checker_finds_mistakes(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "a.json").write_text(json.dumps({
                "K": ["Fine line.", "Fine line.", "", "Broken {System line", "Hello {Sys tem}", "Say hi to Curd Nerd"],
                "Ok": ["All good {System}."]}), encoding="utf-8")
            (Path(folder) / "eoc.json").write_text(json.dumps({"E": ["Curd Nerd is allowed here."]}), encoding="utf-8")
            serious, _ = check_dialogue.check(folder)
            text = "\n".join(serious)
            self.assertIn("twice", text)
            self.assertIn("empty line", text)
            self.assertEqual(text.count("broken braces"), 2)
            self.assertIn("real person", text)
            self.assertNotIn("eoc.json", text)


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "data"
        self.data.mkdir()
        (self.data / "mood.json").write_text('{"score": 5}')
        (self.data / "voice_cache").mkdir()
        (self.data / "voice_cache" / "big.npy").write_text("x" * 100)
        self.backups = self.root / "data_backups"

    def test_first_start_makes_no_backup_but_writes_the_version(self):
        self.assertIsNone(backup.backup_if_new_version(self.data, self.backups, "1.0"))
        self.assertEqual(json.loads((self.data / "data_format.json").read_text())["version"], "1.0")

    def test_same_version_makes_nothing(self):
        backup.backup_if_new_version(self.data, self.backups, "1.0")
        self.assertIsNone(backup.backup_if_new_version(self.data, self.backups, "1.0"))
        self.assertFalse(self.backups.exists())

    def test_a_new_version_copies_the_data_but_not_the_big_caches(self):
        backup.backup_if_new_version(self.data, self.backups, "1.0")
        made = backup.backup_if_new_version(self.data, self.backups, "1.1", now=datetime(2026, 11, 6, 21, 0, 0))
        self.assertTrue(made.name.startswith("1.0-"))
        self.assertTrue((made / "mood.json").is_file())
        self.assertFalse((made / "voice_cache").exists())
        self.assertEqual(json.loads((self.data / "data_format.json").read_text())["version"], "1.1")

    def test_only_the_newest_few_are_kept(self):
        import os
        version = "1.0"
        backup.backup_if_new_version(self.data, self.backups, version)
        for number in range(1, 7):
            backup.backup_if_new_version(self.data, self.backups, "1.%d" % number, now=datetime(2026, 11, number, 9, 0, 0))
            for folder in self.backups.iterdir():                      # make older ones really older
                os.utime(folder, (folder.stat().st_mtime, folder.stat().st_mtime))
        self.assertLessEqual(len(list(self.backups.iterdir())), backup.KEEP_BACKUPS)


class MigrationTests(unittest.TestCase):
    def test_steps_run_once_in_order_and_are_remembered(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            order = []
            steps = [(2, lambda d: order.append(2)), (1, lambda d: order.append(1))]
            self.assertEqual(backup.run_migrations(data, steps, current=2), 2)
            self.assertEqual(order, [1, 2])
            self.assertEqual(backup.run_migrations(data, steps, current=2), 0)       # nothing left to do
            self.assertEqual(json.loads((data / "data_format.json").read_text())["format"], 2)

    def test_a_failing_step_leaves_the_data_at_its_old_format(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)

            def broken(d):
                raise ValueError("nope")
            self.assertEqual(backup.run_migrations(data, [(1, lambda d: None), (2, broken)], current=2), 1)
            self.assertEqual(json.loads((data / "data_format.json").read_text())["format"], 1)


class DiagnosticsTests(unittest.TestCase):
    def test_secrets_are_removed_and_logs_included(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings = root / "settings.json"
            settings.write_text(json.dumps({"updates": {"token": "ghp_" + "a" * 30, "repo": "x/y"},
                                            "streaming": {"youtube_key": "AIza" + "b" * 35, "twitch_channel": "me"},
                                            "tts": {"speed": 1.0}, "empty": {"token": ""}}))
            logs = root / "logs"
            logs.mkdir()
            (logs / "starling.log").write_text("line one\nline two\n", encoding="utf-8")
            data = root / "data"
            data.mkdir()
            (data / "mood.json").write_text("{}")
            out = diagnostics.make_bundle(settings, logs, data, "9.9.9", root / "out")
            with zipfile.ZipFile(out) as bundle:
                names = bundle.namelist()
                text = bundle.read("settings-without-secrets.json").decode()
                self.assertFalse(diagnostics.looks_like_secret(text))
                self.assertIn("twitch_channel", text)
                self.assertIn('"repo": "x/y"', text)
                self.assertEqual(json.loads(text)["empty"]["token"], "")
                self.assertIn("logs/starling.log", names)
                self.assertIn("mood.json", bundle.read("about.json").decode())


class SettingsCheckTests(unittest.TestCase):
    def test_the_defaults_are_clean(self):
        from core.settings import DEFAULTS, check_settings
        checked, problems = check_settings(DEFAULTS, DEFAULTS)
        self.assertEqual(problems, [])
        self.assertEqual(checked, DEFAULTS)

    def test_wrong_kinds_are_fixed_or_reset(self):
        from core.settings import check_settings
        defaults = {"a": {"on": True, "count": 5, "ratio": 0.5, "name": "", "items": [1], "sub": {"x": 1}}}
        saved = {"a": {"on": "yes", "count": "40", "ratio": "high", "name": 7, "items": "nope", "sub": 3}}
        checked, problems = check_settings(saved, defaults)
        self.assertIs(checked["a"]["on"], True)                 # 'yes' read as a switch
        self.assertEqual(checked["a"]["count"], 40)             # '40' read as a number
        self.assertEqual(checked["a"]["ratio"], 0.5)            # 'high' is not a number: default
        self.assertEqual(checked["a"]["name"], 7)               # text settings are left alone
        self.assertEqual(checked["a"]["items"], [1])
        self.assertEqual(checked["a"]["sub"], {"x": 1})
        self.assertEqual(len(problems), 5)

    def test_a_bool_is_not_a_number(self):
        from core.settings import check_settings
        checked, problems = check_settings({"n": True}, {"n": 3})
        self.assertEqual(checked["n"], 3)
        self.assertEqual(len(problems), 1)

    def test_typos_in_known_groups_are_reported(self):
        from core.settings import check_settings
        _, problems = check_settings({"g": {"enabld": True}}, {"g": {"enabled": True}})
        self.assertEqual(len(problems), 1)
        self.assertIn("did you mean g.enabled", problems[0])

    def test_loading_a_damaged_value_keeps_her_running(self):
        from core.settings import Settings
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            path.write_text(json.dumps({"tts": {"volume": "loud"}, "speech": {"enabled": "off"}}))
            loaded = Settings(path).load()
            self.assertIs(loaded.get("speech.enabled"), False)
            self.assertIsInstance(loaded.get("tts.volume"), (int, float))
            self.assertTrue(loaded.problems)


if __name__ == "__main__":
    unittest.main()
