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


if __name__ == "__main__":
    unittest.main()
