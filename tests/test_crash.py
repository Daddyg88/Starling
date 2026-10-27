import tempfile
import unittest
from pathlib import Path

from core import crash


class LeftBehind(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())

    def test_a_clean_run_says_nothing(self):
        (self.folder / crash.FLAG_FILE).write_text("2026-10-27 19:43:00\nversion 0.71.0\n", encoding="utf-8")
        crash.mark_clean_exit(self.folder)
        self.assertEqual(crash.report_previous(self.folder), "")

    def test_a_missing_marker_file_is_fine(self):
        crash.mark_clean_exit(self.folder)                       # nothing to remove: no error
        self.assertEqual(crash.report_previous(self.folder), "")

    def test_a_marker_that_was_left_means_it_did_not_stop_cleanly(self):
        (self.folder / crash.FLAG_FILE).write_text("2026-10-27 19:43:00\nversion 0.71.0\n", encoding="utf-8")
        said = crash.report_previous(self.folder)
        self.assertIn("did not stop cleanly", said)
        self.assertIn("19:43:00", said)

    def test_the_old_crash_report_is_copied_into_the_log_and_kept_once(self):
        (self.folder / crash.CRASH_FILE).write_text("Windows fatal exception: access violation\nThread 0x1 (most recent call first):\n", encoding="utf-8")
        with self.assertLogs("starling.crash", level="WARNING") as seen:
            said = crash.report_previous(self.folder)
        self.assertTrue(said)
        self.assertIn("access violation", "\n".join(seen.output))
        self.assertFalse((self.folder / crash.CRASH_FILE).exists())
        self.assertTrue((self.folder / crash.LAST_CRASH_FILE).exists())
        self.assertEqual(crash.report_previous(self.folder), "")        # not reported twice


class Hooks(unittest.TestCase):
    def test_an_uncaught_thread_error_is_written_with_its_traceback(self):
        import sys
        import threading
        folder = Path(tempfile.mkdtemp())
        old_hooks = (sys.excepthook, threading.excepthook, crash._handle, dict(crash._state))
        try:
            crash._handle = None
            self.assertTrue(crash.install(folder, version="0.71.0"))
            self.assertTrue((folder / crash.FLAG_FILE).exists())

            def boom():
                raise ValueError("the thread broke")
            with self.assertLogs("starling.crash", level="CRITICAL") as seen:
                thread = threading.Thread(target=boom, name="test-thread")
                thread.start()
                thread.join()
            self.assertIn("the thread broke", "\n".join(seen.output))
            self.assertIn("test-thread", "\n".join(seen.output))
            self.assertIn("the thread broke", (folder / crash.CRASH_FILE).read_text(encoding="utf-8"))
            crash.mark_clean_exit(folder)
            self.assertFalse((folder / crash.FLAG_FILE).exists())
        finally:
            import faulthandler
            faulthandler.disable()
            if crash._handle is not None:
                crash._handle.close()
            sys.excepthook, threading.excepthook, crash._handle = old_hooks[0], old_hooks[1], old_hooks[2]
            crash._state.clear()
            crash._state.update(old_hooks[3])


if __name__ == "__main__":
    unittest.main()
