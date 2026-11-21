"""Asking her what she remembers: your pets, your likes, the moments she kept, and 'what do you remember about me' (all of it together)."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from memory.habits import HabitKeeper
from memory.profile import PlayerProfile
from memory.recall import MemoryRecall
from tests.test_dialogue import FakeSpeech, real_dialogue
from tests.test_memory import Base


class AskBase(Base):
    def setUp(self):
        super().setUp()
        self.speech = FakeSpeech()
        self.profile = PlayerProfile(Path(self.tmp.name) / "p.json")
        self.habits = HabitKeeper(None, Path(self.tmp.name) / "h.json", announce=lambda k, v: None, now=lambda: datetime(2026, 11, 20, 12, 0))
        self.recall = MemoryRecall(self.store, real_dialogue(), self.settings, speech=self.speech, profile=self.profile, habits=self.habits)

    def ask(self, text):
        return self.recall.try_handle(text)


class PetQuestions(AskBase):
    def setUp(self):
        super().setUp()
        self.profile.learn("we have two cats called milo and luna")
        self.profile.learn("my dog is called rex")

    def test_the_many_ways_of_asking_about_a_pet(self):
        for text, must in (("do you remember my dog", "Rex"), ("how is my dog", "Rex"), ("hows my dog", "Rex"), ("tell me about my cats", "Milo"),
                           ("what do you remember about my cats", "Luna"), ("do you remember my pets", "Rex"), ("what pets do i have", "Milo"),
                           ("do i have a dog", "Rex"), ("who is rex", "Rex"), ("how is luna", "Luna"), ("do you remember milo", "Milo")):
            reply = self.ask(text)
            self.assertIsNotNone(reply, text)
            self.assertIn(must, reply, text)

    def test_the_answer_is_spoken(self):
        reply = self.ask("how is my dog")
        self.assertEqual(self.speech.said[-1]["text"], reply)

    def test_a_kind_she_does_not_know(self):
        reply = self.ask("do i have a hamster")
        self.assertIn("hamster", reply)
        self.assertIn("Rex", reply)

    def test_no_pets_at_all(self):
        for p in list(self.profile.pets):
            self.profile.remove("pet", p["name"])
        self.assertIn("pet", self.ask("do i have a dog").lower())

    def test_an_unnamed_pet(self):
        for p in list(self.profile.pets):
            self.profile.remove("pet", p["name"])
        self.profile.learn("i have a parrot")
        self.assertIn("parrot", self.ask("do you remember my parrot"))

    def test_a_stranger_name_is_not_hers_to_answer(self):
        self.assertIsNone(self.ask("who is zebediah"))


class LikeQuestions(AskBase):
    def setUp(self):
        super().setUp()
        self.profile.learn("i love pizza")
        self.profile.learn("i hate mining")

    def test_one_thing(self):
        self.assertIn("pizza", self.ask("do i like pizza"))
        self.assertIn("mining", self.ask("do i like mining"))
        self.assertIn("sprouts", self.ask("do i like sprouts"))

    def test_the_whole_list(self):
        self.assertIn("pizza", self.ask("do you know what i like"))
        self.assertIn("mining", self.ask("do you remember what i hate"))


class MomentQuestions(AskBase):
    def test_a_record_when_she_has_it(self):
        self.fire("FSDJump", StarSystem="Colonia", JumpDist=60)
        self.assertIn("Colonia", self.ask("what was my longest jump"))
        self.assertIn("Colonia", self.ask("do you remember my longest jump"))

    def test_a_record_when_she_does_not(self):
        reply = self.ask("what was my biggest mission")
        self.assertTrue(reply)
        self.assertNotIn("?", reply)

    def test_hours_and_deaths(self):
        self.store.raise_stat("hours_together", 12.5)
        self.assertIn("12.5", self.ask("how long have we been playing"))
        self.fire("Died")
        self.assertTrue(self.ask("how many times have i died"))

    def test_unrelated_chat_is_left_alone(self):
        for text in ("what is the weather", "my longest day", "how is the ship"):
            self.assertIsNone(self.ask(text), text)


class EverythingTogether(AskBase):
    def test_what_do_you_remember_includes_what_you_told_her_and_the_moments(self):
        self.profile.learn("my dog is called rex")
        self.profile.learn("i love pizza")
        self.fire("FSDJump", StarSystem="Colonia", JumpDist=60)
        for question in ("what do you remember", "what do you remember about me", "what do you know about me", "what have i told you"):
            reply = self.ask(question)
            self.assertIn("Rex", reply, question)
            self.assertIn("pizza", reply, question)
        self.assertIn("Colonia", self.ask("what do you remember about me"))

    def test_the_favourite_dock_is_remembered_but_never_the_carrier(self):
        self.habits.stations = {"Jameson Memorial": {"count": 12, "recent": [], "last": "2026-11-20"}, "J7T-8XL": {"count": 30, "recent": [], "last": "2026-11-20"}}
        self.habits.home_names = lambda: ("J7T-8XL",)
        reply = self.ask("what do you remember")
        self.assertIn("Jameson Memorial", reply)
        self.assertNotIn("J7T", reply)

    def test_only_the_profile_switch_hides_the_profile_part(self):
        self.profile.learn("my dog is called rex")
        self.settings.set("brain.profile", False)
        self.assertNotIn("Rex", self.ask("what do you remember") or "")


if __name__ == "__main__":
    unittest.main()
