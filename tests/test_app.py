import tempfile
import unittest
from pathlib import Path

from core.app import App


class AppStartupTests(unittest.TestCase):
    def test_app_starts_and_stops_cleanly(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            app = App(
                settings_path=folder / "settings.json",
                database_path=folder / "test.db",
                logs_dir=folder / "logs",
            )
            app.start()
            report = "\n".join(app.status_report())
            self.assertIn("STARLING is online", report)
            session_id = app.session_id
            self.assertIsNotNone(session_id)
            app.stop()
            self.assertIsNone(app.database)
            # the session should now have an end time (checked with a fresh connection)
            from database.db import Database
            check = Database(folder / "test.db").initialise()
            row = check.fetch_one("SELECT ended_at FROM sessions WHERE id = ?", (session_id,))
            self.assertIsNotNone(row["ended_at"])
            check.close()


if __name__ == "__main__":
    unittest.main()


class AppJournalWiringTests(unittest.TestCase):
    def test_processor_and_event_files_are_ready_after_start(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            app = App(settings_path=folder / "s.json", database_path=folder / "t.db", logs_dir=folder / "logs")
            app.start()
            try:
                self.assertGreater(len(app.registry), 20)
                app.processor.handle_line('{"event":"Died","KillerName":"Test"}')
                rows = app.database.fetch_all("SELECT event_name, summary FROM event_log")
                self.assertEqual([r["event_name"] for r in rows], ["Died"])
            finally:
                app.stop()
