"""The running program's side of updating: check GitHub, download the new version, and say what happened.

It never swaps files itself (they are in use). It downloads and verifies, then the launcher installs the update the
next time Starling starts.
"""
import os
import subprocess
import sys
import threading
from pathlib import Path

from core import paths, updater
from core.updater import UpdateError
from core.version import __version__


class UpdateService:
    RECHECK_FLOOR = 5.0 / 60.0          # never re-check more often than every 5 seconds

    def __init__(self, settings, home=None, fetch=updater.fetch_latest, stage=updater.stage_update):
        self.settings = settings
        self.fetch, self.stage = fetch, stage
        # Under the launcher the layout is  <home>/app (this program)  and  <home>/updates.
        self.updates_dir = Path(home) / "updates" if home else Path(paths.ROOT).parent / "updates"
        self.message = ""
        self._busy = False

    def repo(self):
        return str(self.settings.get("updates.repo", "") or os.environ.get("STARLING_REPO", "")).strip()

    def managed(self):
        """True when Starling was started by Starling.exe (so a downloaded update will be installed on restart)."""
        return bool(os.environ.get("STARLING_LAUNCHER"))

    def waiting(self):
        return updater.pending_version(self.updates_dir)

    def check(self, download=True):
        """Returns a sentence for the screen. Safe to call from any thread."""
        if self._busy:
            return "Already checking."
        self._busy = True
        try:
            token = str(self.settings.get("updates.token", "") or "").strip()
            info = self.fetch(self.repo(), token)
            if not updater.is_newer(info["version"], __version__):
                self.message = "You have the newest version (%s)." % __version__
                return self.message
            if not download:
                self.message = "Version %s is available." % info["version"]
                return self.message
            if not self.managed():
                self.message = ("Version %s is available. Starling was not started from Starling.exe, so download the new "
                                "Starling.exe (or zip) from your GitHub releases page." % info["version"])
                return self.message
            self.stage(info, self.updates_dir, token)
            self.message = "Version %s is downloaded. Close Starling and open Starling.exe again to install it." % info["version"]
            return self.message
        except UpdateError as error:
            self.message = str(error)
            return self.message
        finally:
            self._busy = False

    def check_in_background(self, log=None):
        """Checks now, then again every updates.recheck_minutes (default 30) while she keeps running.
        0.85.9: it used to check ONCE at start, so someone who leaves her running all day never saw a new version."""
        if not self.settings.get("updates.auto_check", True) or not self.repo():
            return None
        self._stop = threading.Event()

        def work():
            last = None
            while not self._stop.is_set():
                try:
                    text = self.check()
                    if log and text != last:                     # say it when it changes, not every half hour
                        log.info("Update check: %s", text)
                    last = text
                except Exception:
                    if log:
                        log.exception("Update check failed")
                try:
                    minutes = float(self.settings.get("updates.recheck_minutes", 30) or 30)
                except (TypeError, ValueError):
                    minutes = 30.0
                if self._stop.wait(max(self.RECHECK_FLOOR, minutes) * 60.0):
                    break
        thread = threading.Thread(target=work, name="update-check", daemon=True)
        thread.start()
        return thread

    def stop(self):
        event = getattr(self, "_stop", None)
        if event is not None:
            event.set()

    def restart_now(self, launcher=None, spawn=subprocess.Popen):
        """Opens Starling.exe a few seconds from now (it installs the waiting update). Returns (ok, sentence).
        The caller then closes the dashboard. Needs the launcher's path, which newer Starling.exe files pass along."""
        launcher = launcher or os.environ.get("STARLING_LAUNCHER_EXE", "")
        if not self.waiting():
            return False, "There is no downloaded update waiting."
        if not launcher or not os.path.isfile(launcher):
            return False, "Update %s is ready. Close Starling and open Starling.exe again to install it." % self.waiting()
        try:
            flags = 0x08000000 | 0x00000008 if sys.platform == "win32" else 0        # no window, detached
            spawn('cmd /c "ping -n 4 127.0.0.1 >nul & start "" "%s""' % launcher, shell=True, creationflags=flags)
        except Exception as error:
            return False, "I could not restart by myself (%s). Close Starling and open Starling.exe again." % error
        return True, "Restarting to install %s..." % self.waiting()
