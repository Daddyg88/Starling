import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from control.bind_backup import BindBackup, KEEP_COPIES


class Settings:
    def __init__(self, **v): self.v = v
    def get(self, k, d=None): return self.v.get(k, d)


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.game, self.dest = root / "Bindings", root / "backups"
        self.game.mkdir()
        (self.game / "Custom.4.0.binds").write_text("<Root>one</Root>", encoding="utf-8")
        self.t = [datetime(2026, 11, 1, 12, 0, 0)]
        self.clock = [0.0]
        self.b = BindBackup(None, Settings(), lambda: self.game, self.dest, now=lambda: self.t[0], clock=lambda: self.clock[0])

    def tick(self):
        self.t[0] += timedelta(minutes=1)

    def test_first_backup_copies_and_second_is_skipped(self):
        first = self.b.backup()
        self.assertTrue((first / "Custom.4.0.binds").exists())
        self.assertIsNone(self.b.backup())
        self.assertEqual(len(list(self.dest.iterdir())), 1)

    def test_a_change_makes_a_new_copy_and_original_is_untouched(self):
        self.b.backup()
        self.tick()
        (self.game / "Custom.4.0.binds").write_text("<Root>two two</Root>", encoding="utf-8")
        self.assertIsNotNone(self.b.backup())
        self.assertEqual((self.game / "Custom.4.0.binds").read_text(encoding="utf-8"), "<Root>two two</Root>")
        self.assertEqual(len(list(self.dest.iterdir())), 2)

    def test_a_new_start_does_not_duplicate_identical_files(self):
        self.b.backup()
        again = BindBackup(None, Settings(), lambda: self.game, self.dest, now=lambda: self.t[0])
        self.assertIsNone(again.backup())

    def test_only_newest_copies_kept(self):
        for i in range(KEEP_COPIES + 5):
            (self.game / "Custom.4.0.binds").write_text("<Root>%d</Root>" % i, encoding="utf-8")
            self.tick()
            self.b._seen_stamp = None
            self.b.backup()
        self.assertEqual(len(list(self.dest.iterdir())), KEEP_COPIES)

    def test_off_missing_folder_and_throttle(self):
        off = BindBackup(None, Settings(**{"binds.backup": False}), lambda: self.game, self.dest)
        self.assertIsNone(off.backup())
        self.assertIsNone(BindBackup(None, Settings(), lambda: None, self.dest).backup())
        self.assertIsNone(BindBackup(None, Settings(), lambda: self.game / "nope", self.dest).backup())
        self.b.on_event(None)
        self.assertEqual(len(list(self.dest.iterdir())), 1)
        (self.game / "Custom.4.0.binds").write_text("<Root>x y z</Root>", encoding="utf-8")
        self.tick()
        self.b.on_event(None)                                      # too soon: ignored
        self.assertEqual(len(list(self.dest.iterdir())), 1)
        self.clock[0] += 601
        self.b.on_event(None)
        self.assertEqual(len(list(self.dest.iterdir())), 2)


if __name__ == "__main__":
    unittest.main()
