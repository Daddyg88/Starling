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
