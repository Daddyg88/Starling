import subprocess
import unittest
from unittest import mock

from navigation import route


class ClipboardTests(unittest.TestCase):
    def test_clip_gets_every_handle_so_no_console_is_needed(self):
        with mock.patch.object(route.os, "name", "nt"), mock.patch.object(route.subprocess, "run") as run:
            self.assertTrue(route.copy_to_clipboard("Sol"))
        kwargs = run.call_args.kwargs
        self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)

    def test_falls_back_to_the_windows_clipboard(self):
        with mock.patch.object(route.os, "name", "nt"), \
                mock.patch.object(route.subprocess, "run", side_effect=OSError(50, "not supported")), \
                mock.patch.object(route, "_copy_with_ctypes", return_value=True) as direct:
            self.assertTrue(route.copy_to_clipboard("Sol"))
        direct.assert_called_once_with("Sol")

    def test_both_failing_returns_false(self):
        with mock.patch.object(route.os, "name", "nt"), \
                mock.patch.object(route.subprocess, "run", side_effect=OSError(50, "x")), \
                mock.patch.object(route, "_copy_with_ctypes", side_effect=OSError("no")):
            self.assertFalse(route.copy_to_clipboard("Sol"))

    def test_nothing_to_copy(self):
        self.assertFalse(route.copy_to_clipboard(""))
