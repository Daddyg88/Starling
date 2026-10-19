import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from core.event_bus import EventBus
from core.settings import Settings
from database.db import Database
from journal.event_logger import EventLogger
from tests.test_dialogue import real_dialogue
from tests.test_kokoro import FakePipeline, FakeSound, ok_setup
from tts.base_tts import VoiceSettings
from tts.kokoro_tts import KokoroTTS
from tts.speech_manager import SpeechManager
from tts.voice_warmer import VoiceWarmer, priority_order


class EventLoggerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Database(Path(self.tmp.name) / "t.db").initialise()
        self.addCleanup(self.db.close)
        self.sid = self.db.execute("INSERT INTO sessions DEFAULT VALUES")
        self.bus = EventBus()
        self.logger = EventLogger(self.db, self.sid)
        self.logger.attach(self.bus)
        self.addCleanup(self.logger.stop)

    def names(self):
        return [r["event_name"] for r in self.db.fetch_all("SELECT event_name FROM event_log ORDER BY id")]

    def test_events_are_saved_in_order(self):
        for name in ("A", "B", "C"):
            self.bus.publish(name, {"summary": name.lower()})
        self.logger.flush()
        self.assertEqual(self.names(), ["A", "B", "C"])

    def test_publishing_does_not_wait_for_the_disk(self):
        gate = threading.Event()
        real = self.db.execute_many

        def slow(sql, rows):
            gate.wait(2)
            real(sql, rows)

        self.db.execute_many = slow
        started = time.monotonic()
        for i in range(50):
            self.bus.publish("E%d" % i, {})
        self.assertLess(time.monotonic() - started, 0.5)       # the writer is stuck, the bus is not
        gate.set()
        self.logger.flush()
        self.assertEqual(len(self.names()), 50)

    def test_stop_writes_what_is_left(self):
        self.bus.publish("Last", {})
        self.logger.stop()
        self.assertEqual(self.names(), ["Last"])

    def test_internal_events_are_not_saved(self):
        self.bus.publish("speech.finished", {})
        self.bus.publish("app.started", {})
        self.logger.flush()
        self.assertEqual(self.names(), [])

    def test_a_full_queue_drops_instead_of_blocking(self):
        self.logger.stop()
        for i in range(2100):
            self.bus.publish("E", {})
        self.assertGreater(self.logger.dropped, 0)

    def test_database_failure_is_survivable(self):
        def broken(sql, rows):
            raise RuntimeError("disk full")
        self.db.execute_many = broken
        with self.assertLogs("starling.event_logger", level="ERROR"):
            self.bus.publish("X", {})
            self.logger.flush()
        self.assertTrue(self.logger._thread.is_alive())


class DatabaseTests(unittest.TestCase):
    def test_pragmas_and_batch(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "t.db").initialise()
            try:
                self.assertEqual(db.fetch_one("PRAGMA synchronous")[0], 1)      # NORMAL
                self.assertEqual(db.fetch_one("PRAGMA journal_mode")[0], "wal")
                sid = db.execute("INSERT INTO sessions DEFAULT VALUES")
                db.execute_many("INSERT INTO event_log (session_id, event_name, summary) VALUES (?, ?, ?)",
                                [(sid, "A", None), (sid, "B", None)])
                self.assertEqual(db.fetch_one("SELECT COUNT(*) AS n FROM event_log")["n"], 2)
            finally:
                db.close()


class Cache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.pipe = FakePipeline()
        self.tts = KokoroTTS(self.dir / "p.pt", self.dir / "r.mp3", pipeline_factory=lambda: self.pipe,
                             torch_load=lambda p: "PACK", sound_module=FakeSound(), setup_function=ok_setup,
                             cache_dir=self.dir / "cache")
        self.tts.start_loading()
        self.tts.wait_until_loaded(5)


class KokoroSpeedTests(Cache):
    def test_is_cached(self):
        self.assertFalse(self.tts.is_cached("Hello there."))
        self.tts.render("Hello there.")
        self.assertTrue(self.tts.is_cached("Hello there."))

    def test_start_delay_is_measured(self):
        self.tts.speak("Hello there.", VoiceSettings())
        self.assertGreaterEqual(self.tts.last_start_delay, 0.0)

    def test_a_slow_start_is_logged(self):
        with self.assertLogs("starling.kokoro", level="INFO") as logs:
            self.tts._note_start_delay(2.5, "Something long")
        self.assertIn("Slow start", logs.output[0])


class WarmerTests(Cache):
    def setUp(self):
        super().setUp()
        self.settings = Settings(self.dir / "s.json").load()
        self.dialogue = real_dialogue()
        self.free = [True]
        self.warmer = VoiceWarmer(self.tts, self.dialogue, self.settings, free_provider=lambda: self.free[0], sleep=lambda s: None)

    def test_everyday_lines_come_first(self):
        texts = priority_order(self.dialogue, False, self.settings)
        first_jump = [l.text.split("||")[0].strip() for l in self.dialogue.lines["Docked"] if "{" not in l.text.split("||")[0]]
        self.assertIn(first_jump[0], texts[:200])
        self.assertEqual(len(texts), len(set(texts)))
        self.assertTrue(all("{" not in t for t in texts))

    def test_stops_when_asked_and_skips_cached(self):
        texts = priority_order(self.dialogue, False, self.settings)
        self.tts.render(texts[0])
        done = threading.Event()
        calls = []
        real = self.tts.render

        def counting(text, speed=1.0):
            calls.append(text)
            if len(calls) >= 3:
                self.warmer.stop()
                done.set()
            return real(text, speed)

        self.tts.render = counting
        self.warmer.start()
        self.assertTrue(done.wait(5))
        thread = self.warmer._thread
        if thread is not None:
            thread.join(5)
        self.assertNotIn(texts[0], calls)
        self.assertEqual(calls[0], texts[1])

    def test_waits_while_the_cpu_is_busy(self):
        self.free[0] = False
        self.assertFalse(self.warmer.may_work())
        self.free[0] = True
        self.assertTrue(self.warmer.may_work())

    def test_waits_while_she_is_talking(self):
        self.warmer.speech = SimpleNamespace(is_busy=lambda: True)
        self.assertFalse(self.warmer.may_work())

    def test_switched_off(self):
        self.settings.set("tts.warm_cache", "off")
        self.assertFalse(self.warmer.may_work())
        self.warmer.force = True
        self.assertTrue(self.warmer.may_work())             # the dashboard button still works

    def test_status_sentences(self):
        self.assertIn("Waiting", self.warmer.status())
        self.warmer.total, self.warmer.made = 10, 4
        self.assertIn("4 of 10", self.warmer.status())
        self.warmer.finished = True
        self.assertIn("fully prepared", self.warmer.status())


class InterruptTests(unittest.TestCase):
    def test_interrupt_stops_chatter_but_not_warnings(self):
        from tests.test_tts import FakeProvider
        slow = FakeProvider("kokoro", duration=3.0)
        manager = SpeechManager({"kokoro": slow}, Settings(Path(tempfile.gettempdir()) / "nope.json").load())
        manager.start()
        try:
            manager.say(text="Chatting away about nothing.", priority="normal")
            self.assertTrue(slow.started.wait(2))
            started = time.monotonic()
            self.assertTrue(manager.interrupt())
            self.assertTrue(manager.wait_until_idle(2))
            self.assertLess(time.monotonic() - started, 2)
            slow.started.clear()
            manager.say(text="Hull critical!", priority="critical")
            self.assertTrue(slow.started.wait(2))
            self.assertFalse(manager.interrupt())            # a safety warning is never cut off
        finally:
            manager.stop()


if __name__ == "__main__":
    unittest.main()
