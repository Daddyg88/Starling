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
        self.launcher.start_dashboard()
        kind, args, kw = self.ran[-1]
        self.assertEqual(kw["env"]["STARLING_REPO"], "Ben/Starling")
        self.assertIn("--dashboard", args[0])


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
