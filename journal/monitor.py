"""
One background thread that polls the journal and Status.json once a second.
Using a single thread keeps STARLING's resource use tiny.
"""

import threading
import time

from core.logger import get_logger
from journal.status_reader import StatusReader
from journal.watcher import JournalWatcher

log = get_logger("monitor")

STALE_STATUS_SECONDS = 180     # Status.json older than this at start-up: Elite is not running


def hide_if_game_closed(status_path, state, now=None):
    """
    Starling reads the last journal quietly when she starts. If Elite is not running, that journal is old news (and often has no
    "Shutdown" line, for example after a crash), so the overlays would show the last system for no reason. Mark the game as closed;
    the next jump or load-in shows them again. Returns True when it did.
    """
    try:
        age = (time.time() if now is None else now) - status_path.stat().st_mtime
    except (OSError, AttributeError):
        age = None                       # no Status.json at all: the game has never run here
    if age is None or age > STALE_STATUS_SECONDS:
        if state is not None and not getattr(state, "game_quit", False):
            state.game_quit = True
            return True
    return False


class JournalMonitor:
    def __init__(self, folder, processor, bus=None, poll_seconds=1.0):
        self.folder = folder
        self.poll_seconds = max(0.2, float(poll_seconds))
        self.journal = JournalWatcher(folder, processor, bus)
        self.status = StatusReader(folder, processor)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._fast_until = 0.0
        self._thread = None

    FAST_SECONDS = 0.1

    def look_fast(self, seconds):
        """Looks at the journal ten times a second for the next `seconds` (0 = back to normal at once). For short jobs that wait on
        the game's answer, like sub targeting; the rest of the time the slow, cheap one-second rate is used."""
        self._fast_until = time.monotonic() + seconds if seconds > 0 else 0.0
        self._wake.set()                      # do not sleep out the rest of the current second

    def start(self):
        self._thread = threading.Thread(target=self._run, name="journal-monitor", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)

    def _run(self):
        log.info("Journal monitor started (checking every %.1f s)", self.poll_seconds)
        first = True
        while not self._stop.is_set():
            try:
                self.journal.poll_once()
                self.status.poll_once()
                if first:
                    first = False
                    if hide_if_game_closed(self.status.path, getattr(self.journal.processor, "state", None)):
                        log.info("Elite is not running: the overlays stay hidden until you load in")
            except Exception:
                # Never let one bad moment kill the monitor.
                log.exception("Problem while checking the journal")
            self._wait()
        log.info("Journal monitor stopped")

    def _wait(self):
        """Sleeps until the next look: 0.1 s while look_fast is on, else poll_seconds. Status.json is only read at the normal rate."""
        if time.monotonic() < self._fast_until:
            end = time.monotonic() + self.poll_seconds
            while not self._stop.is_set() and time.monotonic() < min(end, self._fast_until):
                self._wake.clear()
                self._stop.wait(self.FAST_SECONDS)
                try:
                    self.journal.poll_once()
                except Exception:
                    log.exception("Problem while checking the journal")
            return
        self._wake.clear()
        if not self._stop.is_set():
            self._wake.wait(self.poll_seconds)
