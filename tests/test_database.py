import sqlite3
import tempfile
import unittest
from pathlib import Path

from database.db import Database

EXPECTED_TABLES = {
    "conversations", "event_log", "lifetime_stats", "memories",
    "notification_log", "relationship", "relationship_history",
    "schema_version", "sessions", "settings",
}


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "test.db"
        self.db = Database(self.path).initialise()

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def test_all_tables_created(self):
        self.assertTrue(EXPECTED_TABLES.issubset(set(self.db.table_names())))

    def test_starting_relationship_values(self):
        row = self.db.fetch_one("SELECT * FROM relationship WHERE id = 1")
        self.assertEqual(
            (row["trust"], row["patience"], row["affection"], row["respect"]),
            (50, 100, 25, 50),
        )

    def test_starting_lifetime_stats_are_zero(self):
        row = self.db.fetch_one("SELECT * FROM lifetime_stats WHERE id = 1")
        self.assertEqual(row["missions_completed"], 0)
        self.assertEqual(row["hours_together"], 0)

    def test_running_setup_twice_is_safe(self):
        self.db.close()
        again = Database(self.path).initialise()
        self.assertEqual(again.schema_version(), 1)
        rows = again.fetch_all("SELECT * FROM relationship")
        self.assertEqual(len(rows), 1)
        again.close()
        self.db = Database(self.path).initialise()  # so tearDown has something to close

    def test_values_outside_0_to_100_are_rejected(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE relationship SET trust = 150 WHERE id = 1")

    def test_data_survives_restart(self):
        self.db.execute(
            "INSERT INTO memories (memory_type, summary) VALUES (?, ?)",
            ("test", "First jump together"),
        )
        self.db.close()
        self.db = Database(self.path).initialise()
        row = self.db.fetch_one("SELECT summary FROM memories")
        self.assertEqual(row["summary"], "First jump together")


if __name__ == "__main__":
    unittest.main()
