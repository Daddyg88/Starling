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
            self.assertEqual(second.recap(), {"when": "yesterday", "summary": "18 jumps and 1 kill", "where": "Sol"})
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
            self.assertEqual(third.recap(), {"when": "2 days ago", "summary": "1 jump", "where": "Sol"})

    def test_nothing_to_say_for_no_record_or_a_very_old_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(self.make(tmp, datetime(2026, 11, 9)).recap())
            old = self.make(tmp, datetime(2026, 1, 1))
            old.on_event(ev("FSDJump", StarSystem="Sol"))
            old.flush()
            self.assertIsNone(self.make(tmp, datetime(2026, 11, 9)).recap())


class SessionHistory(unittest.TestCase):
    """0.96.71: each play session is a one-line record (jumps, kills, deaths, docks, minutes, where it ended, chat size)."""

    def make(self, folder, day, clock=None):
        return StatsKeeper(None, Path(folder) / "stats.json", announce=lambda k, v: None, now=lambda: day, clock=clock or (lambda: 0.0))

    def play(self, keeper, jumps=0, deaths=0, docks=0, kills=0, system="Sol"):
        for _ in range(jumps):
            keeper.on_event(ev("FSDJump", StarSystem=system))
        for _ in range(deaths):
            keeper.on_event(ev("Died"))
        for _ in range(docks):
            keeper.on_event(ev("Docked", StationName="X"))
        for _ in range(kills):
            keeper.on_event(ev("Bounty"))

    def test_the_record_has_where_it_ended_deaths_and_chat(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = [0.0]
            first = self.make(tmp, datetime(2026, 11, 8, 20, 0), clock=lambda: now[0])
            now[0] = 7200.0                                        # two hours later
            first.chat_people = lambda: 42
            self.play(first, jumps=5, deaths=2, docks=3, system="Colonia")
            first.flush()
            row = first.sessions()[0]
            self.assertEqual((row["jumps"], row["deaths"], row["docks"], row["system"], row["people"]), (5, 2, 3, "Colonia", 42))
            self.assertEqual(row["minutes"], 120)
            second = self.make(tmp, datetime(2026, 11, 9, 19, 0))
            self.assertEqual(second.recap(), {"when": "yesterday", "summary": "5 jumps", "where": "Colonia", "deaths": 2, "people": 42})

    def test_small_things_are_left_out_of_the_recap(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.make(tmp, datetime(2026, 11, 8, 20, 0))
            first.chat_people = lambda: 3                          # a quiet chat is not worth mentioning
            self.play(first, jumps=2, deaths=1)                    # one death is not worth mentioning
            first.flush()
            found = self.make(tmp, datetime(2026, 11, 9, 19, 0)).recap()
            self.assertNotIn("people", found)
            self.assertNotIn("deaths", found)

    def test_old_files_without_the_new_fields_still_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "stats.json").write_text(json.dumps({"last_session": {"ended": "2026-11-08", "jumps": 4, "kills": 1}}), encoding="utf-8")
            found = self.make(tmp, datetime(2026, 11, 9)).recap()
            self.assertEqual(found, {"when": "yesterday", "summary": "4 jumps and 1 kill"})

    def test_history_keeps_the_newest_few_and_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            for day in range(1, 21):
                keeper = self.make(tmp, datetime(2026, 11, day, 20, 0))
                self.play(keeper, jumps=day)
                keeper.flush()
            keeper = self.make(tmp, datetime(2026, 11, 21, 20, 0))
            rows = keeper.sessions()
            self.assertEqual(len(rows), 14)
            self.assertEqual([r["jumps"] for r in rows][:2], [20, 19])

    def test_forget_one_or_all_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            for day in (1, 2, 3):
                keeper = self.make(tmp, datetime(2026, 11, day, 20, 0))
                self.play(keeper, jumps=day)
                keeper.flush()
            keeper = self.make(tmp, datetime(2026, 11, 4, 20, 0))
            ids = [r["id"] for r in keeper.sessions()]
            self.assertTrue(keeper.forget_session(ids[0]))         # the newest, which is also "last time"
            self.assertEqual(len(keeper.sessions()), 2)
            self.assertIsNone(keeper.recap())
            self.assertFalse(keeper.forget_session("nope"))
            keeper.forget_sessions()
            self.assertEqual(keeper.sessions(), [])
            again = self.make(tmp, datetime(2026, 11, 5, 20, 0))
            self.assertEqual(again.sessions(), [])
            self.assertIsNone(again.recap())
