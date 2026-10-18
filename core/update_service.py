"""The running program's side of updating: check GitHub, download the new version, and say what happened.

It never swaps files itself (they are in use). It downloads and verifies, then the launcher installs the update the
next time Starling starts.
"""
import os
import threading
from pathlib import Path

from core import paths, updater
from core.updater import UpdateError
from core.version import __version__


class UpdateService:
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
        if not self.settings.get("updates.auto_check", True) or not self.repo():
            return None

        def work():
            try:
                text = self.check()
                if log:
                    log.info("Update check: %s", text)
            except Exception:
                if log:
                    log.exception("Update check failed")
        thread = threading.Thread(target=work, name="update-check", daemon=True)
        thread.start()
        return thread
