import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from core.event_bus import Event
from memory.stats import StatsKeeper
from tests.test_brain import Base


class Day:
    d = datetime(2026, 11, 1, 12, 0)

    def __call__(self):
        return self.d


def ev(name, **data):
    return Event(name=name, data=data)


class KeeperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "stats.json"
        self.day = Day()
        self.said = []
        self.keeper = StatsKeeper(None, self.path, announce=lambda k, v: self.said.append((k, v)), now=self.day)

    def test_visits_count_and_remember_the_last_one(self):
        self.keeper.on_event(ev("FSDJump", StarSystem="Sol"))
        self.assertEqual(self.keeper.visit_info("Sol"), (1, ""))
        self.day.d = datetime(2026, 11, 3)
        self.keeper.on_event(ev("FSDJump", StarSystem="Sol"))
        self.assertEqual(self.keeper.visit_info("Sol"), (2, "2026-11-01"))
        self.assertEqual(self.keeper.visit_info("Nowhere"), (0, ""))

    def test_kills_today_and_total_and_milestone(self):
        for _ in range(50):
            self.keeper.on_event(ev("Bounty"))
        self.assertEqual((self.keeper.kills_today(), self.keeper.kills_total), (50, 50))
        self.assertEqual(self.said, [("Stats_KillMilestone", {"Number": "50"})])
        self.day.d = datetime(2026, 11, 2)
        self.keeper.on_event(ev("FactionKillBond"))
        self.assertEqual((self.keeper.kills_today(), self.keeper.kills_total), (1, 51))

    def test_terraformables_are_counted_once(self):
        for _ in range(2):
            self.keeper.on_event(ev("Scan", BodyName="A 1", TerraformState="Terraformable"))
        self.keeper.on_event(ev("Scan", BodyName="A 2", TerraformState=""))
        self.assertEqual(self.keeper.terraformable, ["A 1"])

    def test_saved_and_loaded(self):
        self.keeper.on_event(ev("FSDJump", StarSystem="Sol"))
        self.keeper.on_event(ev("Bounty"))
        self.keeper.flush()
        again = StatsKeeper(None, self.path, now=self.day)
        self.assertEqual((again.jumps_total, again.kills_total, again.visit_info("Sol")[0]), (1, 1, 1))

    def test_bad_file_is_ignored(self):
        self.path.write_text("not json", encoding="utf-8")
        self.assertEqual(StatsKeeper(None, self.path).kills_total, 0)
        self.path.write_text(json.dumps({"kills_total": "x", "visits": []}), encoding="utf-8")
        self.assertEqual(StatsKeeper(None, self.path).kills_total, 0)

    def test_odd_events_do_not_crash(self):
        self.keeper.on_event(SimpleNamespace(name="FSDJump", data=None))
        self.keeper.on_event(ev("Scan"))


class VoiceTests(Base):
    def setUp(self):
        super().setUp()
        tmp = tempfile.mkdtemp()
        self.keeper = StatsKeeper(None, Path(tmp) / "s.json")
        self.brain.stats = self.keeper

    def said(self):
        return " ".join(i.get("text", "") if isinstance(i, dict) else str(i) for i in self.speech.said)

    def test_kills(self):
        self.ask("how many kills have I got")
        self.assertIn("haven't counted", self.said())
        self.speech.said.clear()
        for _ in range(3):
            self.keeper.on_event(ev("Bounty"))
        self.ask("how many kills have i got")
        self.assertIn("3", self.said())

    def test_visits(self):
        for text in ("how many times have i been here", "have i been here before"):
            self.speech.said.clear()
            self.ask(text)
            self.assertIn("Sol", self.said(), text)
        self.keeper.on_event(ev("FSDJump", StarSystem="Sol"))
        self.keeper.on_event(ev("FSDJump", StarSystem="Sol"))
        self.speech.said.clear()
        self.ask("how many times have i been here")
        self.assertIn("2", self.said())

    def test_jumps_and_terraformables(self):
        self.ask("how many jumps have i made")
        self.assertIn("haven't counted", self.said())
        self.speech.said.clear()
        self.ask("how many terraformable worlds have i found")
        self.assertIn("No terraformable", self.said())

    def test_switched_off(self):
        self.settings.set("stats.enabled", False)
        self.ask("how many kills have i got")
        self.assertIn("not keeping count", self.said())


if __name__ == "__main__":
    unittest.main()


class RecapTests(unittest.TestCase):
    """0.89.9: the start-up line about the last play session."""

    def make(self, folder, day):
        return StatsKeeper(None, Path(folder) / "stats.json", announce=lambda k, v: None, now=lambda: day)

    def test_last_session_is_remembered_and_told_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.make(tmp, datetime(2026, 11, 8, 20, 0))
            for _ in range(18):
                first.on_event(ev("FSDJump", StarSystem="Sol"))
            first.on_event(ev("Bounty"))
            first.flush()
            second = self.make(tmp, datetime(2026, 11, 9, 19, 0))
            self.assertEqual(second.recap(), {"when": "yesterday", "summary": "18 jumps and 1 kill"})
            self.assertIsNone(second.recap())                      # only once per start

    def test_an_empty_session_does_not_wipe_the_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.make(tmp, datetime(2026, 11, 8, 20, 0))
            first.on_event(ev("FSDJump", StarSystem="Sol"))
            first.flush()
            quiet = self.make(tmp, datetime(2026, 11, 9, 19, 0))
            quiet._dirty = True
            quiet.flush()                                          # a start with nothing done in it
            third = self.make(tmp, datetime(2026, 11, 10, 19, 0))
            self.assertEqual(third.recap(), {"when": "2 days ago", "summary": "1 jump"})

    def test_nothing_to_say_for_no_record_or_a_very_old_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(self.make(tmp, datetime(2026, 11, 9)).recap())
            old = self.make(tmp, datetime(2026, 1, 1))
            old.on_event(ev("FSDJump", StarSystem="Sol"))
            old.flush()
            self.assertIsNone(self.make(tmp, datetime(2026, 11, 9)).recap())
