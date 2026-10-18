"""
One background thread that polls the journal and Status.json once a second.
Using a single thread keeps STARLING's resource use tiny.
"""

import threading

from core.logger import get_logger
from journal.status_reader import StatusReader
from journal.watcher import JournalWatcher

log = get_logger("monitor")


class JournalMonitor:
    def __init__(self, folder, processor, bus=None, poll_seconds=1.0):
        self.folder = folder
        self.poll_seconds = max(0.2, float(poll_seconds))
        self.journal = JournalWatcher(folder, processor, bus)
        self.status = StatusReader(folder, processor)
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, name="journal-monitor", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)

    def _run(self):
        log.info("Journal monitor started (checking every %.1f s)", self.poll_seconds)
        while not self._stop.is_set():
            try:
                self.journal.poll_once()
                self.status.poll_once()
            except Exception:
                # Never let one bad moment kill the monitor.
                log.exception("Problem while checking the journal")
            self._stop.wait(self.poll_seconds)
        log.info("Journal monitor stopped")
