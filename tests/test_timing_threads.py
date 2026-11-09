import unittest

from control import keys
from core import timing


class Woz0859Tests(unittest.TestCase):
    def test_hash_key_known(self):
        self.assertTrue(keys.is_known("Hash"))

    def test_busiest_threads_text(self):
        text = timing.busiest_threads({1: 0.0, 2: 0.0}, {1: 5.0, 2: 0.1, 3: 9.0}, {1: "worker"})
        self.assertIn("worker 5.0 s", text)
        self.assertIn("native thread 3 9.0 s", text)
        self.assertNotIn("native thread 2", text)

    def test_thread_cpu_times_never_raises(self):
        self.assertIsInstance(timing.thread_cpu_times(), dict)


if __name__ == "__main__":
    unittest.main()


class OwnerNames(unittest.TestCase):
    def test_unnamed_threads_show_where_they_started(self):
        from core import timing
        text = timing.busiest_threads({1: 0.0, 2: 0.0}, {1: 9.0, 2: 6.0}, {1: "MainThread"}, owner=lambda tid: "ctranslate2.dll")
        self.assertIn("MainThread 9.0 s", text)
        self.assertIn("native thread 2 (started in ctranslate2.dll) 6.0 s", text)

    def test_unknown_owner_and_errors_are_harmless(self):
        from core import timing
        self.assertIn("native thread 2 6.0 s", timing.busiest_threads({}, {2: 6.0}, {}, owner=lambda tid: ""))
        def boom(tid):
            raise OSError("no")
        self.assertIn("native thread 2 6.0 s", timing.busiest_threads({}, {2: 6.0}, {}, owner=boom))

    def test_not_windows_gives_nothing(self):
        import sys
        from core import timing
        if sys.platform != "win32":
            self.assertEqual(timing.thread_owner(123), "")
