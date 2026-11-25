import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from core import move_home


def build_install(root, big=b"x" * 5000):
    root = Path(root)
    (root / "app" / "data").mkdir(parents=True)
    (root / "app" / "main.py").write_text("print(1)")
    (root / "app" / "data" / "tetko.db").write_bytes(big)
    (root / "app" / "empty_folder").mkdir()
    (root / ".venv" / "Scripts").mkdir(parents=True)
    (root / ".venv" / "Scripts" / "python.exe").write_bytes(b"MZ")
    (root / "launcher.log").write_text("log")
    return root


def plenty(path):
    return SimpleNamespace(free=500 * (1 << 30))


class MoveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.old = build_install(self.tmp / "C" / "Starling")
        self.new = self.tmp / "D" / "Starling"
        self.pointer = self.tmp / "C" / "Starling" / "install_location.txt"        # the note lives in the default (old) folder here
        self.pointer.write_text(str(self.old))
        self.patch = mock.patch("shutil.disk_usage", plenty)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_a_good_move_copies_checks_switches_and_deletes_the_old_copy(self):
        seen = []
        ok, text = move_home.move(self.old, self.new, self.pointer, say=seen.append, venv_ok=lambda p: True)
        self.assertTrue(ok, text)
        self.assertEqual((self.new / "app" / "data" / "tetko.db").read_bytes(), b"x" * 5000)
        self.assertTrue((self.new / "app" / "empty_folder").is_dir())            # empty folders come along
        self.assertEqual(self.pointer.read_text(), str(self.new))                 # Starling.exe will look there next time
        self.assertFalse((self.old / "app").exists())                             # the old copy is gone...
        self.assertTrue(self.pointer.exists())                                    # ...except the note that says where she is
        self.assertTrue(any("100%" in line for line in seen))

    def test_a_move_when_the_note_lives_somewhere_else(self):
        note = self.tmp / "default" / "install_location.txt"
        ok, text = move_home.move(self.old, self.new, note, venv_ok=lambda p: True)
        self.assertTrue(ok, text)
        self.assertEqual(note.read_text(), str(self.new))
        self.assertFalse(self.old.exists())

    def test_a_failed_copy_changes_nothing(self):
        calls = []

        def breaks(src, dst):
            calls.append(src)
            if len(calls) == 3:
                raise OSError("disk full")
            Path(dst).write_bytes(Path(src).read_bytes())
        ok, text = move_home.move(self.old, self.new, self.pointer, copy_file=breaks, venv_ok=lambda p: True)
        self.assertFalse(ok)
        self.assertIn("Nothing was changed", text)
        self.assertFalse(self.new.exists())                                        # the half copy is removed
        self.assertEqual(self.pointer.read_text(), str(self.old))                  # still pointing at the old place
        self.assertTrue((self.old / "app" / "data" / "tetko.db").exists())         # the old copy is untouched

    def test_a_copy_that_does_not_match_is_not_accepted(self):
        def short(src, dst):
            Path(dst).write_bytes(b"")                                              # writes empty files
        ok, text = move_home.move(self.old, self.new, self.pointer, copy_file=short, venv_ok=lambda p: True)
        self.assertFalse(ok)
        self.assertTrue((self.old / "app" / "main.py").exists())
        self.assertEqual(self.pointer.read_text(), str(self.old))

    def test_a_private_python_that_will_not_start_is_dropped_so_it_is_rebuilt(self):
        ok, text = move_home.move(self.old, self.new, self.pointer, venv_ok=lambda p: False)
        self.assertTrue(ok)
        self.assertIn("rebuild", text)
        self.assertFalse((self.new / ".venv").exists())
        self.assertTrue((self.new / "app" / "main.py").exists())

    def test_the_target_is_checked(self):
        self.assertFalse(move_home.check_target(self.old, self.old / "inside")[0])           # inside the old folder
        self.assertFalse(move_home.check_target(self.old, self.tmp / "C")[0])                # contains the old folder
        self.assertFalse(move_home.check_target(self.old, Path("relative"))[0])              # not a full path
        full = self.tmp / "full"
        full.mkdir()
        (full / "a.txt").write_text("x")
        self.assertIn("not empty", move_home.check_target(self.old, full)[1])
        with mock.patch("shutil.disk_usage", lambda p: SimpleNamespace(free=1000)):
            ok, why = move_home.check_target(self.old, self.new)
        self.assertFalse(ok)
        self.assertIn("Not enough room", why)
        self.assertTrue(move_home.check_target(self.old, self.new)[0])

    def test_where_the_install_is(self):
        home, why = move_home.current_home(self.old / "app", environ={})
        self.assertEqual(home, self.old)
        self.assertIsNone(move_home.current_home(self.old / "app", environ={"STARLING_HOME": "D:\\x"})[0])
        self.assertIsNone(move_home.current_home(self.tmp, environ={})[0])                   # a source folder, not the installed layout
        self.assertEqual(move_home.with_starling_name(Path("D:/Games")).name, "Starling")
        self.assertEqual(move_home.with_starling_name(Path("D:/Starling")), Path("D:/Starling"))

    def test_the_helper_is_started_from_a_copy_in_the_temp_folder(self):
        spawned = []
        ok, text = move_home.start_move(self.old, self.new, "C:/Starling.exe", spawn=lambda cmd, **kw: spawned.append(cmd),
                                        python="py.exe", wait_pid=1234)
        self.assertTrue(ok)
        cmd = spawned[0]
        self.assertEqual(cmd[0], "py.exe")
        self.assertTrue(Path(cmd[1]).exists())
        self.assertNotIn(str(self.old), cmd[1])                                              # not run from the folder being moved
        for part in ("--from", str(self.old), "--to", str(self.new), "--wait-pid", "1234", "--launch", "C:/Starling.exe"):
            self.assertIn(part, cmd)

    def test_the_move_button_is_on_the_updates_page(self):
        from pathlib import Path as P
        source = P(__file__).resolve().parent.parent.joinpath("ui", "dashboard.py").read_text(encoding="utf-8")
        self.assertIn("Move Starling to another drive or folder", source)
        self.assertIn("def move_install", source)


if __name__ == "__main__":
    unittest.main()
