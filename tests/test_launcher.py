import tempfile
import urllib.error as urllib_error
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


class CertificateRetry(unittest.TestCase):
    """Some Windows PCs fail with 'unable to get issuer certificate' for GitHub: the check tries again with the certifi list."""

    def test_retries_once_with_a_checked_context_on_a_certificate_error(self):
        import ssl
        from unittest import mock
        calls = []

        def opener(request, timeout=0, context=None):
            calls.append(context)
            if context is None:
                raise urllib_error.URLError(ssl.SSLCertVerificationError("unable to get issuer certificate"))
            return "ok"
        with mock.patch.object(updater, "_certifi_context", return_value=object()):
            self.assertEqual(updater._open("https://api.github.com/x", opener=opener), "ok")
        self.assertEqual(len(calls), 2)
        self.assertIsNone(calls[0])
        self.assertIsNotNone(calls[1])

    def test_other_errors_are_not_retried(self):
        from unittest import mock
        calls = []

        def opener(request, timeout=0, context=None):
            calls.append(1)
            raise urllib_error.URLError("no internet")
        with mock.patch.object(updater, "_certifi_context", return_value=object()):
            with self.assertRaises(urllib_error.URLError):
                updater._open("https://api.github.com/x", opener=opener)
        self.assertEqual(len(calls), 1)

    def test_without_certifi_the_original_error_comes_back(self):
        import ssl
        from unittest import mock

        def opener(request, timeout=0, context=None):
            raise urllib_error.URLError(ssl.SSLCertVerificationError("unable to get issuer certificate"))
        with mock.patch.object(updater, "_certifi_context", return_value=None):
            with self.assertRaises(urllib_error.URLError):
                updater._open("https://api.github.com/x", opener=opener)


class DesktopShortcutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.layout = L.Layout(Path(self.tmp.name) / "Starling")
        self.layout.home.mkdir(parents=True)
        self.layout.app.mkdir(parents=True)
        self.ran = []
        self.code = 0

        def run(cmd, **kw):
            self.ran.append((cmd, kw))
            return SimpleNamespace(returncode=self.code, stdout="", stderr="boom")
        self.launcher = L.Launcher(self.layout, lambda text: None, repo="x/y", run=run)

    def test_makes_one_shortcut_with_the_exe_and_the_icon(self):
        icon = self.layout.app / "ui" / "assets"
        icon.mkdir(parents=True)
        (icon / "starling.ico").write_bytes(b"ico")
        self.assertTrue(self.launcher.make_desktop_shortcut(exe="C:/Games/Starling.exe", windows=True))
        command, kwargs = self.ran[0]
        self.assertEqual(command[0], "powershell")
        self.assertEqual(kwargs["env"]["STARLING_LNK_TARGET"], "C:/Games/Starling.exe")
        self.assertTrue(kwargs["env"]["STARLING_LNK_ICON"].endswith("starling.ico"))
        self.assertIn("GetFolderPath('Desktop')", command[-1])
        self.assertTrue((self.layout.home / "desktop_shortcut.done").exists())

    def test_only_once_so_a_deleted_shortcut_stays_deleted(self):
        self.assertTrue(self.launcher.make_desktop_shortcut(exe="C:/S.exe", windows=True))
        self.assertFalse(self.launcher.make_desktop_shortcut(exe="C:/S.exe", windows=True))
        self.assertEqual(len(self.ran), 1)

    def test_falls_back_to_the_exes_own_icon(self):
        self.launcher.make_desktop_shortcut(exe="C:/S.exe", windows=True)
        self.assertEqual(self.ran[0][1]["env"]["STARLING_LNK_ICON"], "C:/S.exe,0")

    def test_not_on_other_systems_or_when_not_the_exe(self):
        self.assertFalse(self.launcher.make_desktop_shortcut(exe="/x/Starling", windows=False))
        self.assertFalse(self.launcher.make_desktop_shortcut(exe="", windows=True))
        self.assertEqual(self.ran, [])

    def test_can_be_switched_off(self):
        (self.layout.app / "config").mkdir()
        (self.layout.app / "config" / "settings.json").write_text('{"app": {"desktop_shortcut": false}}', encoding="utf-8")
        self.assertFalse(self.launcher.make_desktop_shortcut(exe="C:/S.exe", windows=True))
        self.assertEqual(self.ran, [])

    def test_a_failure_is_quiet_and_tried_again_next_time(self):
        self.code = 1
        self.assertFalse(self.launcher.make_desktop_shortcut(exe="C:/S.exe", windows=True))
        self.assertFalse((self.layout.home / "desktop_shortcut.done").exists())

    def test_an_exception_never_escapes(self):
        def broken(cmd, **kw):
            raise OSError("no powershell")
        self.launcher.run = broken
        self.assertFalse(self.launcher.make_desktop_shortcut(exe="C:/S.exe", windows=True))


class IconFilesTests(unittest.TestCase):
    def test_the_icon_files_exist_and_are_real_pictures(self):
        from PIL import Image
        assets = Path(__file__).resolve().parent.parent / "ui" / "assets"
        ico = Image.open(assets / "starling.ico")
        self.assertIn((256, 256), ico.info.get("sizes", {(256, 256)}))
        for name in ("starling_logo.png", "starling_emblem.png", "starling_emblem_alpha.png"):
            self.assertGreater(Image.open(assets / name).width, 200, name)



class InstalledUpdaterTests(unittest.TestCase):
    """Starling.exe must use the update code of the installed app, so an old exe's bug can be cured by an update."""

    def setUp(self):
        import sys
        self.sys = sys
        self.saved = (L.updater, L.UpdateError, list(sys.modules["core"].__path__),
                      sys.modules.get("core.updater"), sys.modules.get("core.secure_open"))

    def tearDown(self):
        L.updater, L.UpdateError = self.saved[0], self.saved[1]
        self.sys.modules["core"].__path__ = self.saved[2]
        for name, module in (("core.updater", self.saved[3]), ("core.secure_open", self.saved[4])):
            if module is not None:
                self.sys.modules[name] = module

    def make_app(self, updater_text):
        import tempfile
        from pathlib import Path
        folder = Path(tempfile.mkdtemp()) / "app"
        (folder / "core").mkdir(parents=True)
        (folder / "core" / "updater.py").write_text(updater_text, encoding="utf-8")
        (folder / "core" / "secure_open.py").write_text("X = 1\n", encoding="utf-8")
        return folder

    def test_installed_copy_is_used(self):
        good = ("class UpdateError(Exception):\n    pass\nMARK = 'installed'\n"
                "def fetch_latest(*a, **k): pass\ndef stage_update(*a, **k): pass\n"
                "def apply_pending(*a, **k): pass\ndef is_newer(*a, **k): return True\n")
        self.assertTrue(L.use_installed_updater(self.make_app(good)))
        self.assertEqual(L.updater.MARK, "installed")
        self.assertIs(L.UpdateError, L.updater.UpdateError)

    def test_broken_copy_falls_back(self):
        before = L.updater
        self.assertFalse(L.use_installed_updater(self.make_app("this is not python (\n")))
        self.assertIs(L.updater, before)
        self.assertFalse(L.use_installed_updater(self.make_app("MARK = 1\n")))
        self.assertIs(L.updater, before)

    def test_no_installed_copy(self):
        import tempfile
        self.assertFalse(L.use_installed_updater(tempfile.mkdtemp()))
