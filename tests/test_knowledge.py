import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from core.event_bus import Event
from database.db import Database
from memory.habits import HabitKeeper
from memory.knowledge import Knowledge, session_text
from memory.profile import PlayerProfile
from memory.stats import StatsKeeper
from memory.store import MemoryStore
from personality.people import People


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        folder = Path(self.tmp.name)
        self.db = Database(folder / "t.db").initialise()
        self.addCleanup(self.db.close)
        self.store = MemoryStore(self.db)
        self.profile = PlayerProfile(folder / "profile.json")
        self.people = People(folder / "people.json")
        self.habits = HabitKeeper(None, folder / "habits.json", announce=lambda k, v: True, now=lambda: datetime(2026, 11, 9, 12, 0),
                                  hours=lambda: 0, jumps=lambda: 0)
        self.stats = StatsKeeper(None, folder / "stats.json", announce=lambda k, v: None, now=lambda: datetime(2026, 11, 9, 12, 0))
        self.know = Knowledge(self.store, self.profile, self.people, self.habits, self.stats)

    def texts(self, group=None):
        return [e.text for e in self.know.entries() if group is None or e.group == group]

    def find(self, text):
        return [e for e in self.know.entries() if e.text == text][0]


class Listing(Base):
    def test_empty_means_no_groups(self):
        self.assertEqual(self.know.grouped(), [])

    def test_everything_is_listed_in_its_group(self):
        self.profile.learn("i love pizza")
        self.profile.learn("i hate mining")
        self.profile.learn("my dog is called rex")
        self.profile.learn("my favourite colour is blue")
        self.people.learn("my friend andrew", "my friend Andrew")
        self.store.add("death", "You were destroyed by Bob in Sol")
        self.store.increment("systems_visited", 5)
        for _ in range(4):
            self.habits.on_event(Event(name="Docked", data={"StationName": "Jameson Memorial"}))
        self.stats.on_event(Event(name="FSDJump", data={"StarSystem": "Colonia"}))
        names = [g for g, _ in self.know.grouped()]
        self.assertEqual(names, ["You told me", "People", "Moments", "Habits", "Sessions", "Totals"])
        self.assertIn("You like pizza", self.texts("You told me"))
        self.assertIn("You dislike mining", self.texts("You told me"))
        self.assertIn("You have a dog called Rex", self.texts("You told me"))
        self.assertIn("Your favourite colour is blue", self.texts("You told me"))
        self.assertTrue(any(t.startswith("Andrew, your friend") for t in self.texts("People")))
        self.assertIn("You were destroyed by Bob in Sol", self.texts("Moments"))
        self.assertIn("You often dock at Jameson Memorial (4 times)", self.texts("Habits"))
        self.assertTrue(self.texts("Sessions")[0].startswith("2026-11-09: 1 jump"))
        self.assertFalse([e for e in self.know.entries() if e.group == "Totals"][0].can_forget)

    def test_missing_parts_do_not_stop_the_list(self):
        know = Knowledge(None, self.profile, None, None, None)
        self.profile.learn("i love pizza")
        self.assertEqual([e.text for e in know.entries()], ["You like pizza"])
        self.assertEqual(Knowledge().entries(), [])

    def test_a_broken_part_is_skipped(self):
        class Broken:
            @property
            def likes(self):
                raise RuntimeError("boom")
        know = Knowledge(self.store, Broken(), self.people, None, None)
        self.store.add("death", "You were destroyed in Sol")
        self.assertEqual([e.group for e in know.entries()], ["Moments"])

    def test_session_text(self):
        row = {"ended": "2026-11-08", "jumps": 18, "kills": 1, "deaths": 2, "docks": 0, "minutes": 130, "system": "Colonia", "people": 42}
        self.assertEqual(session_text(row), "2026-11-08: 18 jumps, 1 kill, 2 deaths, about 2 hours, ended in Colonia, 42 people in chat")
        self.assertEqual(session_text({"ended": "2026-11-08"}), "2026-11-08: a short session")


class Forgetting(Base):
    def test_forget_each_kind_one_by_one(self):
        self.profile.learn("i love pizza")
        self.profile.learn("i love chips")
        self.profile.learn("i hate mining")
        self.profile.learn("my dog is called rex")
        self.profile.learn("my favourite colour is blue")
        self.people.learn("my friend andrew", "my friend Andrew")
        self.store.add("death", "You were destroyed in Sol")
        self.store.add("death", "You were destroyed in Lave")
        for _ in range(4):
            self.habits.on_event(Event(name="Docked", data={"StationName": "Jameson Memorial"}))
        for entry in [self.find("You like pizza"), self.find("You dislike mining"), self.find("You have a dog called Rex"),
                      self.find("Your favourite colour is blue"), self.find("You were destroyed in Sol"),
                      self.find("You often dock at Jameson Memorial (4 times)")]:
            self.assertTrue(self.know.forget(entry), entry.text)
        andrew = [e for e in self.know.entries() if e.group == "People"][0]
        self.assertTrue(self.know.forget(andrew))
        left = self.texts()
        self.assertEqual(left, ["You like chips", "You were destroyed in Lave"])
        # and it stays forgotten after a restart
        again = PlayerProfile(Path(self.tmp.name) / "profile.json")
        self.assertEqual((again.likes, again.dislikes, again.pets, again.favourites), (["chips"], [], [], {}))
        self.assertEqual(People(Path(self.tmp.name) / "people.json").items, {})

    def test_forgetting_something_that_is_gone_says_so(self):
        self.profile.learn("i love pizza")
        entry = self.find("You like pizza")
        self.assertTrue(self.know.forget(entry))
        self.assertFalse(self.know.forget(entry))

    def test_a_total_cannot_be_forgotten_one_by_one(self):
        self.store.increment("systems_visited", 5)
        total = [e for e in self.know.entries() if e.group == "Totals"][0]
        self.assertFalse(self.know.forget(total))
        self.assertEqual(self.store.stats()["systems_visited"], 5)

    def test_forget_a_session(self):
        self.stats.on_event(Event(name="FSDJump", data={"StarSystem": "Colonia"}))
        entry = [e for e in self.know.entries() if e.group == "Sessions"][0]
        self.assertTrue(self.know.forget(entry))
        self.assertEqual(self.stats.sessions(), [])


class AppWiring(unittest.TestCase):
    def test_forget_everything_also_clears_sessions(self):
        import inspect
        from core.app import App
        source = inspect.getsource(App.forget_memories)
        self.assertIn("forget_sessions", source)
        self.assertTrue(hasattr(App, "knowledge"))


if __name__ == "__main__":
    unittest.main()
