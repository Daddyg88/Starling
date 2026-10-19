"""
STARLING's database (one SQLite file: data/tetko.db).

How upgrades work: every change to the database design is a numbered
"migration" in the list below. On start-up STARLING applies any migrations
it hasn't applied yet, so future updates never wipe your saved memories.
NEVER edit an old migration. To change the design later, add a new one.
"""

import sqlite3
import threading

from core import paths
from core.logger import get_logger

log = get_logger("database")

MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS relationship (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    trust       REAL NOT NULL DEFAULT 50  CHECK (trust     BETWEEN 0 AND 100),
    patience    REAL NOT NULL DEFAULT 100 CHECK (patience  BETWEEN 0 AND 100),
    affection   REAL NOT NULL DEFAULT 25  CHECK (affection BETWEEN 0 AND 100),
    respect     REAL NOT NULL DEFAULT 50  CHECK (respect   BETWEEN 0 AND 100),
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO relationship (id, trust, patience, affection, respect)
VALUES (1, 50, 100, 25, 50);

CREATE TABLE IF NOT EXISTS relationship_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trait       TEXT NOT NULL,
    change      REAL NOT NULL,
    new_value   REAL NOT NULL,
    reason      TEXT,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lifetime_stats (
    id                      INTEGER PRIMARY KEY CHECK (id = 1),
    hours_together          REAL    NOT NULL DEFAULT 0,
    missions_completed      INTEGER NOT NULL DEFAULT 0,
    times_destroyed         INTEGER NOT NULL DEFAULT 0,
    systems_visited         INTEGER NOT NULL DEFAULT 0,
    ignored_notifications   INTEGER NOT NULL DEFAULT 0,
    positive_conversations  INTEGER NOT NULL DEFAULT 0,
    negative_conversations  INTEGER NOT NULL DEFAULT 0,
    commander_compliments   INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO lifetime_stats (id) VALUES (1);

CREATE TABLE IF NOT EXISTS memories (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_type       TEXT NOT NULL,
    summary           TEXT NOT NULL,
    system_name       TEXT,
    importance        INTEGER NOT NULL DEFAULT 1,
    times_mentioned   INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_mentioned_at TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    commander_name  TEXT,
    ship            TEXT,
    started_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at        TEXT
);

CREATE TABLE IF NOT EXISTS conversations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER REFERENCES sessions(id),
    speaker     TEXT NOT NULL CHECK (speaker IN ('commander', 'starling')),
    message     TEXT NOT NULL,
    mode        TEXT NOT NULL DEFAULT 'companion'
                CHECK (mode IN ('command', 'companion', 'event')),
    tone        TEXT,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS event_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER REFERENCES sessions(id),
    event_name  TEXT NOT NULL,
    summary     TEXT,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_event_log_created ON event_log(created_at);

CREATE TABLE IF NOT EXISTS notification_log (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    event_name       TEXT NOT NULL,
    priority         TEXT NOT NULL,
    spoken_text      TEXT,
    was_spoken       INTEGER NOT NULL DEFAULT 0,
    was_acknowledged INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

# (version number, SQL). Add new ones to the END of this list only.
MIGRATIONS = [
    (1, MIGRATION_1),
]


class Database:
    def __init__(self, path=None):
        self.path = path or paths.DATABASE_FILE
        self._conn = None
        self._lock = threading.RLock()

    # ---- opening and closing ----
    def open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")  # safer if the app crashes
        self._conn.execute("PRAGMA synchronous = NORMAL")  # with WAL this is still crash-safe, and far fewer slow disk waits
        return self

    def close(self):
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    # ---- first-run set-up and upgrades ----
    def initialise(self):
        """Open the database and bring it up to the newest design."""
        if self._conn is None:
            self.open()
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_version ("
                " version INTEGER PRIMARY KEY,"
                " applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            self._conn.commit()
            current = self.schema_version()
            for version, sql in MIGRATIONS:
                if version > current:
                    log.info("Applying database migration %d", version)
                    self._conn.executescript(sql)
                    self._conn.execute(
                        "INSERT INTO schema_version (version) VALUES (?)", (version,)
                    )
                    self._conn.commit()
        return self

    def schema_version(self):
        row = self.fetch_one("SELECT MAX(version) AS v FROM schema_version")
        return (row["v"] or 0) if row else 0

    # ---- small helpers so other files stay simple ----
    def execute(self, sql, params=()):
        """Run one change (INSERT/UPDATE/DELETE) and save it. Returns the row id."""
        with self._lock:
            cursor = self._conn.execute(sql, params)
            self._conn.commit()
            return cursor.lastrowid

    def execute_many(self, sql, rows):
        """Run the same change for many rows with ONE save to disk (much faster than one at a time)."""
        with self._lock:
            self._conn.executemany(sql, rows)
            self._conn.commit()

    def fetch_one(self, sql, params=()):
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def fetch_all(self, sql, params=()):
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def table_names(self):
        rows = self.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        return [row["name"] for row in rows]
