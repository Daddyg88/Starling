"""
THE MEMORY STORE - what Starling remembers, kept in her database (data/tetko.db) on YOUR computer. Nothing is sent anywhere.

Two kinds of memory:
  * RECORDS  one row per kind that gets replaced when you beat it ("longest jump", "biggest sale").
  * MOMENTS  things that happened ("destroyed by X in Y", "first footfall on Z"). Old ones are trimmed so it never grows forever.
Plus the lifetime counters (hours together, jumps, deaths...) in the lifetime_stats table.
"""
from core.logger import get_logger

log = get_logger("memory")

# kind -> how many of that kind to keep (the newest). Records use 1.
KEEP = {"death": 10, "first_footfall": 60, "big_mission": 20, "milestone": 40}
STATS = ("hours_together", "missions_completed", "times_destroyed", "systems_visited", "ignored_notifications",
         "positive_conversations", "negative_conversations", "commander_compliments")


class MemoryStore:
    def __init__(self, database):
        self.db = database

    # ---- writing ----
    def add(self, kind, summary, system=None, importance=1):
        """Remember a moment. The same summary is never stored twice. Returns the new id or None."""
        summary = str(summary or "").strip()
        if not summary:
            return None
        if self.db.fetch_one("SELECT id FROM memories WHERE memory_type = ? AND summary = ?", (kind, summary)):
            return None
        new_id = self.db.execute(
            "INSERT INTO memories (memory_type, summary, system_name, importance) VALUES (?, ?, ?, ?)",
            (kind, summary, system, int(importance)))
        self._trim(kind)
        return new_id

    def set_record(self, kind, summary, value, system=None, importance=3):
        """Keep ONE record per kind. Replaced only if `value` beats the old one. Returns True if it is a new record."""
        row = self.db.fetch_one("SELECT id, importance FROM memories WHERE memory_type = ?", ("record:" + kind,))
        old = self.record_value(kind)
        if row is not None and old is not None and value <= old:
            return False
        if row is not None:
            self.db.execute("DELETE FROM memories WHERE id = ?", (row["id"],))
        self.db.execute("INSERT INTO memories (memory_type, summary, system_name, importance) VALUES (?, ?, ?, ?)",
                        ("record:" + kind, summary, system, int(importance)))
        self.db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("memory_record_" + kind, repr(float(value))))
        return True

    def record_value(self, kind):
        row = self.db.fetch_one("SELECT value FROM settings WHERE key = ?", ("memory_record_" + kind,))
        try:
            return float(row["value"]) if row else None
        except (TypeError, ValueError):
            return None

    def _trim(self, kind):
        limit = KEEP.get(kind, 30)
        self.db.execute(
            "DELETE FROM memories WHERE memory_type = ? AND id NOT IN "
            "(SELECT id FROM memories WHERE memory_type = ? ORDER BY id DESC LIMIT ?)", (kind, kind, limit))

    def increment(self, stat, amount=1):
        if stat not in STATS:                    # never build SQL from an unknown name
            raise ValueError("unknown stat %r" % stat)
        self.db.execute("UPDATE lifetime_stats SET %s = %s + ? WHERE id = 1" % (stat, stat), (amount,))

    # ---- reading ----
    def stats(self):
        row = self.db.fetch_one("SELECT * FROM lifetime_stats WHERE id = 1")
        return dict(row) if row else {}

    def all(self, limit=500):
        return [dict(r) for r in self.db.fetch_all(
            "SELECT * FROM memories ORDER BY importance DESC, id DESC LIMIT ?", (limit,))]

    def by_kind(self, kind, limit=10):
        return [dict(r) for r in self.db.fetch_all(
            "SELECT * FROM memories WHERE memory_type = ? ORDER BY id DESC LIMIT ?", (kind, limit))]

    def record(self, kind):
        rows = self.by_kind("record:" + kind, 1)
        return rows[0] if rows else None

    def count(self):
        return self.db.fetch_one("SELECT COUNT(*) AS n FROM memories")["n"]

    def least_mentioned(self, kinds, limit=1):
        """The memories of these kinds that she has talked about least (so she doesn't repeat herself)."""
        marks = ",".join("?" for _ in kinds)
        return [dict(r) for r in self.db.fetch_all(
            "SELECT * FROM memories WHERE memory_type IN (%s) ORDER BY times_mentioned ASC, importance DESC, id DESC LIMIT ?" % marks,
            (*kinds, limit))]

    def mentioned(self, memory_id):
        self.db.execute("UPDATE memories SET times_mentioned = times_mentioned + 1, last_mentioned_at = CURRENT_TIMESTAMP "
                        "WHERE id = ?", (memory_id,))

    # ---- forgetting (you are always in charge) ----
    def forget(self, memory_id):
        self.db.execute("DELETE FROM memories WHERE id = ?", (int(memory_id),))

    def forget_everything(self):
        self.db.execute("DELETE FROM memories")
        self.db.execute("DELETE FROM settings WHERE key LIKE 'memory_record_%'")
        self.db.execute("UPDATE lifetime_stats SET hours_together = 0, missions_completed = 0, times_destroyed = 0, "
                        "systems_visited = 0, ignored_notifications = 0, positive_conversations = 0, "
                        "negative_conversations = 0, commander_compliments = 0 WHERE id = 1")
