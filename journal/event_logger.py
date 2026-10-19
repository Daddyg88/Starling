"""
Saves game events into the database (event_log table), so STARLING has a history.

SPEED: writing to disk can take a few milliseconds (much more on a hard drive), and events are handled one after
another. So the events are put in a small queue and a background thread writes them in batches. Nothing else ever
waits for the disk. flush() waits until everything queued has been written (used at shutdown and in tests).
"""
import queue
import threading

from core.logger import get_logger

log = get_logger("event_logger")

KEEP_DAYS = 30
BATCH_SECONDS = 0.5
MAX_QUEUED = 2000
SQL = "INSERT INTO event_log (session_id, event_name, summary) VALUES (?, ?, ?)"


class EventLogger:
    def __init__(self, database, session_id):
        self.database = database
        self.session_id = session_id
        self._queue = queue.Queue(maxsize=MAX_QUEUED)
        self._thread = None
        self._stop = threading.Event()
        self.dropped = 0

    def attach(self, bus):
        bus.subscribe("*", self._on_event)
        self.start()

    def start(self):
        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="event-writer", daemon=True)
            self._thread.start()

    def stop(self):
        """Write everything that is waiting, then stop the writer."""
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=5)
        self._write_all()

    def flush(self):
        """Wait until everything queued so far is in the database."""
        self._queue.join()

    def trim_old(self, days=KEEP_DAYS):
        """Forget log entries older than 'days', so the file never grows forever."""
        self.database.execute(
            "DELETE FROM event_log WHERE created_at < datetime('now', ?)",
            ("-%d days" % days,),
        )

    def _on_event(self, event):
        if event.name.startswith(("app.", "journal.", "speech.", "voice.")):
            return
        try:
            self._queue.put_nowait((self.session_id, event.name, event.data.get("summary")))
        except queue.Full:
            self.dropped += 1                    # the history is nice to have; the game never waits for it

    # ---- the writer ----
    def _take(self, wait):
        rows, tasks = [], 0
        try:
            rows.append(self._queue.get(timeout=wait))
            tasks += 1
            while len(rows) < 200:
                rows.append(self._queue.get_nowait())
                tasks += 1
        except queue.Empty:
            pass
        return rows, tasks

    def _write(self, rows, tasks):
        try:
            if rows:
                self.database.execute_many(SQL, rows)
        except Exception:
            log.exception("Could not save %d events", len(rows))
        finally:
            for _ in range(tasks):
                self._queue.task_done()

    def _write_all(self):
        rows, tasks = self._take(0.01)
        while rows:
            self._write(rows, tasks)
            rows, tasks = self._take(0.01)

    def _run(self):
        while not self._stop.is_set():
            rows, tasks = self._take(BATCH_SECONDS)
            if rows:
                self._write(rows, tasks)
