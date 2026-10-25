import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from core import updater
from core.update_service import UpdateService
from core.settings import Settings
from launcher import launcher as L
from tests.test_updater import GOOD, FakeNet, make_zip, release


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.layout = L.Layout(Path(self.tmp.name) / "Starling")
        self.said = []
        self.ran = []

        def run(cmd, **kw):
            self.ran.append(cmd)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        self.launcher = L.Launcher(self.layout, self.said.append, repo="Ben/Starling", run=run,
                                   popen=lambda *a, **k: self.ran.append(("popen", a, k)))

    def tearDown(self):
        self.tmp.cleanup()

    def net(self, files=None, tag="v0.12.0"):
        return FakeNet(make_zip(files or {**GOOD, "core/version.py": '__version__ = "0.12.0"\n',
                                          "requirements.txt": "customtkinter\n"}), release=release(tag))

    def test_first_run_downloads_and_installs(self):
        with mock.patch.object(updater.urllib.request, "urlopen", self.net()):
            self.launcher.get_newest(first_run=True)
        self.assertTrue((self.layout.app / "main.py").exists())
        self.assertEqual(self.launcher.current_version(), "0.12.0")

    def test_first_run_without_a_repo_explains(self):
        bare = L.Launcher(self.layout, self.said.append, repo="")
        with self.assertRaises(updater.UpdateError):
            bare.get_newest(first_run=True)

    def test_no_update_when_up_to_date(self):
        self.layout.app.mkdir(parents=True)
        (self.layout.app / "core").mkdir()
        (self.layout.app / "core" / "version.py").write_text('__version__ = "0.12.0"\n')
        with mock.patch.object(updater.urllib.request, "urlopen", self.net()):
            self.launcher.get_newest(first_run=False)
        self.assertFalse((self.layout.updates / "pending").exists())

    def test_offline_after_first_run_is_quiet(self):
        self.layout.app.mkdir(parents=True)
        offline = FakeNet(b"", release=None)
        with mock.patch.object(updater.urllib.request, "urlopen", offline):
            self.launcher.get_newest(first_run=False)             # must not raise

    def test_add_ons_install_only_when_requirements_change(self):
        self.layout.app.mkdir(parents=True)
        (self.layout.app / "requirements.txt").write_text("a\n")
        self.layout.python.parent.mkdir(parents=True)
        self.layout.python.write_text("")
        process = SimpleNamespace(stdout=iter(["Collecting a\n"]), wait=lambda: 0)
        self.launcher.popen = lambda *a, **k: process
        self.launcher.install_requirements(self.layout.app)
        self.assertEqual(self.layout.req_mark.read_text(), L.requirements_hash(self.layout.app))
        calls = len(self.ran)
        self.launcher.install_requirements(self.layout.app)
        self.assertEqual(len(self.ran), calls)                   # unchanged: nothing done again

    def test_failed_install_raises_a_plain_message(self):
        self.layout.app.mkdir(parents=True)
        (self.layout.app / "requirements.txt").write_text("a\n")
        self.layout.python.parent.mkdir(parents=True)
        self.layout.python.write_text("")
        self.launcher.popen = lambda *a, **k: SimpleNamespace(stdout=iter([]), wait=lambda: 1)
        with self.assertRaises(RuntimeError):
            self.launcher.install_requirements(self.layout.app)

    def test_start_passes_the_repo_to_the_dashboard(self):
        self.layout.app.mkdir(parents=True)
        seen = {}

        def popen(*a, **k):
            seen.update(args=a, kw=k)
            return SimpleNamespace(poll=lambda: None)
        self.launcher.popen = popen
        self.launcher.start_dashboard(watch_seconds=0)
        self.assertEqual(seen["kw"]["env"]["STARLING_REPO"], "Ben/Starling")
        self.assertNotIn("TCL_LIBRARY", seen["kw"]["env"])
        self.assertIn("--dashboard", seen["args"][0])

    def test_a_dashboard_that_dies_is_explained(self):
        self.layout.app.mkdir(parents=True)

        def popen(cmd, **k):
            k["stdout"].write("Traceback...\nModuleNotFoundError: No module named 'customtkinter'\n")
            k["stdout"].flush()
            return SimpleNamespace(poll=lambda: 1)
        self.launcher.popen = popen
        with self.assertRaises(RuntimeError) as caught:
            self.launcher.start_dashboard(watch_seconds=2)
        self.assertIn("customtkinter", str(caught.exception))


class UpdateServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = Settings(Path(self.tmp.name) / "s.json").load()
        self.settings.set("updates.repo", "Ben/Starling")
        self.staged = []

    def tearDown(self):
        self.tmp.cleanup()

    def service(self, version):
        info = {"version": version, "zip_url": "", "sha_url": ""}
        return UpdateService(self.settings, home=self.tmp.name, fetch=lambda repo, token="": info,
                             stage=lambda i, d, t="": self.staged.append(i))

    def test_up_to_date(self):
        self.assertIn("newest", self.service("0.0.1").check())
        self.assertEqual(self.staged, [])

    def test_newer_but_not_started_from_the_exe_only_says_so(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("STARLING_LAUNCHER", None)
            text = self.service("99.0.0").check()
        self.assertIn("99.0.0", text)
        self.assertEqual(self.staged, [])

    def test_newer_under_the_launcher_is_downloaded(self):
        with mock.patch.dict("os.environ", {"STARLING_LAUNCHER": "1"}):
            text = self.service("99.0.0").check()
        self.assertEqual(len(self.staged), 1)
        self.assertIn("Close Starling", text)

    def test_errors_become_a_message(self):
        def boom(repo, token=""):
            raise updater.UpdateError("Could not reach GitHub: x")
        service = UpdateService(self.settings, home=self.tmp.name, fetch=boom)
        self.assertIn("Could not reach", service.check())

    def test_background_check_needs_a_repo(self):
        self.settings.set("updates.repo", "")
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("STARLING_REPO", None)
            self.assertIsNone(UpdateService(self.settings, home=self.tmp.name).check_in_background())


class CleanEnvTests(unittest.TestCase):
    def test_pyinstaller_tcl_paths_are_not_passed_on(self):
        bad = {"TCL_LIBRARY": r"C:\Temp\_MEI123\_tcl_data", "TK_LIBRARY": "x", "PYTHONPATH": "y", "KEEP": "1"}
        with mock.patch.dict("os.environ", bad):
            env = L.clean_env({"STARLING_LAUNCHER": "1"})
        self.assertNotIn("TCL_LIBRARY", env)
        self.assertNotIn("TK_LIBRARY", env)
        self.assertNotIn("PYTHONPATH", env)
        self.assertEqual(env["KEEP"], "1")
        self.assertEqual(env["STARLING_LAUNCHER"], "1")


class UpdatePromptTests(LauncherTests):
    def test_no_question_by_default(self):
        self.assertFalse(self.launcher.wants_question())

    """The 'Update available' screen: Update now / Not now / always."""

    def old_install(self):
        self.layout.app.mkdir(parents=True)
        (self.layout.app / "core").mkdir()
        (self.layout.app / "core" / "version.py").write_text('__version__ = "0.11.0"\n')
        (self.layout.app / "main.py").write_text("print(1)\n")

    def asking(self, answer):
        self.asked = []

        def ask(info, current):
            self.asked.append((info["version"], current))
            return answer
        self.launcher.ask = ask

    def test_not_now_keeps_the_old_version(self):
        self.old_install()
        self.asking("later")
        (self.layout.app / "config").mkdir()
        (self.layout.app / "config" / "settings.json").write_text('{"updates": {"ask": true}}')   # asking is OFF unless switched on
        with mock.patch.object(updater.urllib.request, "urlopen", self.net()):
            self.launcher.get_newest(first_run=False)
        self.assertEqual(self.asked, [("0.12.0", "0.11.0")])
        self.assertEqual(self.launcher.current_version(), "0.11.0")

    def test_update_now_installs(self):
        self.old_install()
        self.asking("now")
        with mock.patch.object(updater.urllib.request, "urlopen", self.net()):
            self.launcher.get_newest(first_run=False)
        self.assertEqual(self.launcher.current_version(), "0.12.0")

    def test_always_installs_and_stops_asking(self):
        self.old_install()
        self.asking("always")
        with mock.patch.object(updater.urllib.request, "urlopen", self.net()):
            self.launcher.get_newest(first_run=False)
        self.assertEqual(self.launcher.current_version(), "0.12.0")
        self.assertFalse(self.launcher.wants_question())

    def test_no_question_when_up_to_date_or_first_run(self):
        self.asking("later")
        with mock.patch.object(updater.urllib.request, "urlopen", self.net()):
            self.launcher.get_newest(first_run=True)
        self.assertEqual(self.asked, [])
        self.assertEqual(self.launcher.current_version(), "0.12.0")

    def test_no_question_when_you_chose_always(self):
        self.old_install()
        self.launcher.remember_always()
        self.asking("later")
        with mock.patch.object(updater.urllib.request, "urlopen", self.net()):
            self.launcher.get_newest(first_run=False)
        self.assertEqual(self.asked, [])
        self.assertEqual(self.launcher.current_version(), "0.12.0")
