import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.event_bus import Event, EventBus
from core.settings import Settings
from database.db import Database
from memory.keeper import MemoryKeeper, credits
from memory.recall import MemoryRecall
from memory.store import MemoryStore
from personality.greeter import LoginGreeter
from tests.test_dialogue import FakeSpeech, real_dialogue


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Database(Path(self.tmp.name) / "t.db").initialise()
        self.addCleanup(self.db.close)
        self.settings = Settings(Path(self.tmp.name) / "s.json").load()
        self.store = MemoryStore(self.db)
        self.bus = EventBus()
        self.time = [0.0]
        self.state = SimpleNamespace(system="Sol")
        self.keeper = MemoryKeeper(self.bus, self.store, self.settings, lambda: self.state, clock=lambda: self.time[0])
        self.keeper.attach()

    def fire(self, name, **data):
        self.bus.publish(name, data)


class StoreTests(Base):
    def test_add_and_no_duplicates(self):
        self.assertIsNotNone(self.store.add("death", "x"))
        self.assertIsNone(self.store.add("death", "x"))
        self.assertIsNone(self.store.add("death", "  "))
        self.assertEqual(self.store.count(), 1)

    def test_old_moments_are_trimmed(self):
        for n in range(30):
            self.store.add("death", "died %d" % n)
        self.assertEqual(len(self.store.by_kind("death", 100)), 10)
        self.assertEqual(self.store.by_kind("death", 1)[0]["summary"], "died 29")

    def test_record_only_replaced_when_beaten(self):
        self.assertTrue(self.store.set_record("jump", "jump 10", 10))
        self.assertFalse(self.store.set_record("jump", "jump 5", 5))
        self.assertEqual(self.store.record("jump")["summary"], "jump 10")
        self.assertTrue(self.store.set_record("jump", "jump 20", 20))
        self.assertEqual(len(self.store.by_kind("record:jump")), 1)
        self.assertEqual(self.store.record("jump")["summary"], "jump 20")

    def test_unknown_stat_refused(self):
        with self.assertRaises(ValueError):
            self.store.increment("id = 1; DROP TABLE memories; --")

    def test_forget_one_and_everything(self):
        first = self.store.add("death", "a")
        self.store.add("death", "b")
        self.store.set_record("jump", "j", 9)
        self.store.increment("times_destroyed", 3)
        self.store.forget(first)
        self.assertEqual(self.store.count(), 2)
        self.store.forget_everything()
        self.assertEqual(self.store.count(), 0)
        self.assertIsNone(self.store.record_value("jump"))
        self.assertEqual(self.store.stats()["times_destroyed"], 0)
        self.assertTrue(self.store.set_record("jump", "j", 1))     # a fresh start: any value is a record again


class KeeperTests(Base):
    def test_death_is_remembered_and_counted(self):
        self.fire("Died", KillerName="Bob")
        self.assertEqual(self.store.by_kind("death")[0]["summary"], "You were destroyed by Bob in Sol")
        self.assertEqual(self.store.stats()["times_destroyed"], 1)

    def test_longest_jump(self):
        self.fire("FSDJump", StarSystem="A", JumpDist=20.5)
        self.fire("FSDJump", StarSystem="B", JumpDist=10.0)
        self.fire("FSDJump", StarSystem="C", JumpDist=55.25)
        self.assertIn("55.2", self.store.record("longest_jump")["summary"])
        self.assertIn("C", self.store.record("longest_jump")["summary"])
        self.assertEqual(self.store.stats()["systems_visited"], 3)

    def test_biology_and_exploration_records(self):
        self.fire("SellOrganicData", TotalValue=12_500_000)
        self.fire("SellOrganicData", TotalValue=1_000)
        self.fire("SellExplorationData", TotalEarnings=3_000_000)
        self.fire("MultiSellExplorationData", TotalEarnings=9_000_000)
        self.assertIn("12.5 million", self.store.record("biggest_organic_sale")["summary"])
        self.assertIn("9 million", self.store.record("biggest_exploration_sale")["summary"])

    def test_missions(self):
        self.fire("MissionCompleted", LocalisedName="Small", Reward=1000)
        self.fire("MissionCompleted", LocalisedName="Huge", Reward=8_000_000)
        self.assertEqual(self.store.stats()["missions_completed"], 2)
        self.assertEqual(len(self.store.by_kind("big_mission")), 1)

    def test_first_sample_only(self):
        self.fire("ScanOrganic", ScanType="Analyse", Species_Localised="Bacterium X")
        self.assertEqual(self.store.count(), 0)
        self.fire("ScanOrganic", ScanType="Log", Species_Localised="Bacterium X")
        self.fire("ScanOrganic", ScanType="Log", Species_Localised="Bacterium X")
        self.assertEqual(len(self.store.by_kind("first_species")), 1)

    def test_switched_off_saves_nothing(self):
        self.settings.set("memory.enabled", False)
        self.fire("Died", KillerName="Bob")
        self.fire("FSDJump", StarSystem="A", JumpDist=5)
        self.assertEqual(self.store.count(), 0)
        self.assertEqual(self.store.stats()["times_destroyed"], 0)

    def test_hours_saved_once(self):
        self.time[0] = 7200.0
        self.fire("app.stopping")
        self.fire("app.stopping")
        self.assertAlmostEqual(self.store.stats()["hours_together"], 2.0, places=2)

    def test_a_broken_event_does_not_crash(self):
        self.fire("FSDJump", StarSystem="A", JumpDist="far")
        self.fire("Died")
        self.assertEqual(self.store.stats()["times_destroyed"], 1)

    def test_credits_words(self):
        self.assertEqual(credits(2_000_000), "2 million credits")
        self.assertEqual(credits(1_500), "1,500 credits")


class RecallTests(Base):
    def setUp(self):
        super().setUp()
        self.speech = FakeSpeech()
        self.recall = MemoryRecall(self.store, real_dialogue(), self.settings, speech=self.speech)

    def test_empty_memory_answer(self):
        reply = self.recall.try_handle("what do you remember")
        self.assertTrue(reply)
        self.assertEqual(self.speech.said[0]["text"], reply)

    def test_answer_mentions_a_memory(self):
        self.fire("FSDJump", StarSystem="Colonia", JumpDist=60)
        reply = self.recall.try_handle("Starling what do you remember about me")
        self.assertIn("Colonia", reply)
        self.assertEqual(self.store.record("longest_jump")["times_mentioned"], 1)

    def test_unrelated_text_ignored(self):
        self.assertIsNone(self.recall.try_handle("open the galaxy map"))
        self.assertEqual(self.speech.said, [])

    def test_forget_by_voice_is_refused(self):
        self.store.add("death", "x")
        self.assertIn("dashboard", self.recall.try_handle("forget everything"))
        self.assertEqual(self.store.count(), 1)

    def test_login_line_rotates(self):
        self.store.add("death", "You were destroyed by A")
        self.store.add("big_mission", "a mission worth 9 million credits: M")
        first = self.recall.login_line()
        second = self.recall.login_line()
        self.assertTrue(first and second)
        self.assertNotEqual(first.split(":")[-1], second.split(":")[-1])

    def test_login_line_respects_settings(self):
        self.store.add("death", "You were destroyed by A")
        self.settings.set("memory.recall_at_login", False)
        self.assertIsNone(self.recall.login_line())

    def test_login_line_none_when_empty(self):
        self.assertIsNone(self.recall.login_line())


class GreeterTests(Base):
    def test_greeting_includes_a_memory(self):
        self.store.add("big_mission", "a mission worth 9 million credits: Moonshot")
        dialogue = real_dialogue()
        recall = MemoryRecall(self.store, dialogue, self.settings)
        greeter = LoginGreeter(self.bus, FakeSpeech(), dialogue, self.settings, state_provider=lambda: self.state, memory=recall)
        text = greeter.compose({"Ship": "python"}, {"StarSystem": "Sol"})
        self.assertIn("Moonshot", text)

    def test_greeting_survives_a_broken_memory(self):
        class Broken:
            def login_line(self):
                raise RuntimeError("boom")
        greeter = LoginGreeter(self.bus, FakeSpeech(), real_dialogue(), self.settings, state_provider=lambda: self.state, memory=Broken())
        self.assertTrue(greeter.compose({"Ship": "python"}, {"StarSystem": "Sol"}))


if __name__ == "__main__":
    unittest.main()
