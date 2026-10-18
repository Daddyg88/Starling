"""
Follows the newest journal file and feeds new lines to the processor.

Low-resource design: once a second it only asks Windows "how big is the file?".
It reads the file only when it has grown, and only the new part.
"""

import time
from pathlib import Path

from core.logger import get_logger

log = get_logger("watcher")


class JournalWatcher:
    def __init__(self, folder, processor, bus=None, rescan_seconds=30.0):
        self.folder = Path(folder) if folder else None
        self.processor = processor
        self.bus = bus
        self.rescan_seconds = rescan_seconds
        self.current = None            # the journal file we are following
        self._offset = 0               # how much of it we have already read
        self._last_scan = 0.0
        self._dir_mtime = None
        self._first_file = True

    # ---- finding the right file ----
    def _find_latest(self):
        try:
            files = list(self.folder.glob("Journal.*.log"))
        except OSError:
            return None
        if not files:
            return None
        return max(files, key=lambda path: path.stat().st_mtime)

    def _maybe_rescan(self):
        try:
            dir_mtime = self.folder.stat().st_mtime_ns
        except OSError:
            return
        now = time.monotonic()
        due = now - self._last_scan >= self.rescan_seconds
        if self.current is not None and dir_mtime == self._dir_mtime and not due:
            return
        self._dir_mtime = dir_mtime
        self._last_scan = now
        latest = self._find_latest()
        if latest is not None and latest != self.current:
            self._switch_to(latest)

    def _switch_to(self, path):
        # The first file we meet is read "silently": STARLING learns who you are,
        # where you are and what ship you fly, without replaying old news aloud.
        silent = self._first_file
        log.info("Following journal: %s%s", path.name, " (catching up quietly)" if silent else "")
        self.current = path
        self._offset = 0
        self._first_file = False
        if self.bus is not None:
            self.bus.publish("journal.file_changed", {"file": path.name}, "low")
        self._read_new(silent)

    # ---- reading ----
    def _read_new(self, silent):
        try:
            size = self.current.stat().st_size
        except OSError:
            return
        if size < self._offset:
            log.warning("Journal got smaller; starting it again from the top")
            self._offset = 0
        if size == self._offset:
            return
        try:
            with open(self.current, "rb") as handle:
                handle.seek(self._offset)
                while True:
                    raw = handle.readline()
                    if not raw:
                        break
                    if not raw.endswith(b"\n"):
                        break  # half-written line: pick it up next time
                    self._offset += len(raw)
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line:
                        self.processor.handle_line(line, silent)
        except OSError as error:
            log.warning("Could not read %s: %s", self.current.name, error)

    # ---- called once a second by the monitor ----
    def poll_once(self):
        if self.folder is None or not self.folder.is_dir():
            return
        self._maybe_rescan()
        if self.current is not None:
            self._read_new(silent=False)
