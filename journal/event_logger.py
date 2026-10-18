"""Saves game events into the database (event_log table), so STARLING has a history."""

from core.logger import get_logger

log = get_logger("event_logger")

KEEP_DAYS = 30


class EventLogger:
    def __init__(self, database, session_id):
        self.database = database
        self.session_id = session_id

    def attach(self, bus):
        bus.subscribe("*", self._on_event)

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
            self.database.execute(
                "INSERT INTO event_log (session_id, event_name, summary) VALUES (?, ?, ?)",
                (self.session_id, event.name, event.data.get("summary")),
            )
        except Exception:
            log.exception("Could not save event %s", event.name)
