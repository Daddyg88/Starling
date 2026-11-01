"""
Keybind backup: keeps safe copies of your Elite Dangerous key bindings, so a wiped or broken controls setup can be put back.

Whenever the *.binds files in Elite's Bindings folder have changed since the last copy, they are copied (never changed, never
deleted) into  data/bind_backups/<date and time>/  and only the newest 20 copies are kept. It checks when Starling starts and then
at most every 10 minutes while the game runs, using only the files' timestamps, so it costs nothing.

To restore: close Elite, copy the files from the backup folder you want back into
%LOCALAPPDATA%\\Frontier Developments\\Elite Dangerous\\Options\\Bindings   (this is the only place Starling's copies are ever used).
"""
import hashlib
import shutil
import time
from datetime import datetime
from pathlib import Path

from core.logger import get_logger

log = get_logger("bindbackup")

KEEP_COPIES = 20
CHECK_EVERY_SECONDS = 600.0
MAX_FILE_BYTES = 2 * 1024 * 1024


def _binds_files(folder):
    try:
        return sorted(p for p in Path(folder).glob("*.binds") if p.is_file() and p.stat().st_size <= MAX_FILE_BYTES)
    except OSError:
        return []


def fingerprint(files):
    digest = hashlib.sha256()
    for path in files:
        try:
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
        except OSError:
            continue
    return digest.hexdigest()


class BindBackup:
    def __init__(self, bus, settings, folder_provider, dest, now=datetime.now, clock=time.monotonic):
        self.bus, self.settings, self.folder_provider, self.dest = bus, settings, folder_provider, Path(dest)
        self.now, self.clock = now, clock
        self._checked_at = None
        self._seen_stamp = None
        self._last_fingerprint = None
        self.last_backup = None

    def attach(self):
        if self.bus is not None:
            self.bus.subscribe("*", self.on_event)
        self.backup()

    def detach(self):
        if self.bus is not None:
            self.bus.unsubscribe("*", self.on_event)

    def enabled(self):
        return bool(self.settings.get("binds.backup", True))

    def on_event(self, _event):
        if self._checked_at is None or self.clock() - self._checked_at >= CHECK_EVERY_SECONDS:
            self.backup()

    def backup(self):
        """Copies the binds files when they changed. Returns the new backup folder, or None. Never raises."""
        self._checked_at = self.clock()
        if not self.enabled():
            return None
        try:
            folder = self.folder_provider()
            files = _binds_files(folder) if folder else []
            if not files:
                return None
            stamp = tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in files)
            if stamp == self._seen_stamp:
                return None
            self._seen_stamp = stamp
            print_ = fingerprint(files)
            if print_ == self._last_fingerprint or print_ == self._newest_fingerprint():
                self._last_fingerprint = print_
                return None
            target = self.dest / self.now().strftime("%Y-%m-%d_%H-%M-%S")
            target.mkdir(parents=True, exist_ok=True)
            for path in files:
                shutil.copy2(path, target / path.name)
            self._last_fingerprint = print_
            self.last_backup = target
            self._trim()
            log.info("Backed up %d key binding file(s) to %s", len(files), target)
            return target
        except Exception:
            log.exception("The keybind backup failed")
            return None

    def _copies(self):
        try:
            return sorted(p for p in self.dest.iterdir() if p.is_dir())
        except OSError:
            return []

    def _newest_fingerprint(self):
        copies = self._copies()
        return fingerprint(_binds_files(copies[-1])) if copies else None

    def _trim(self):
        copies = self._copies()
        for old in copies[:-KEEP_COPIES]:
            shutil.rmtree(old, ignore_errors=True)
