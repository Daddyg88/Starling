"""Pets: she learns them from ordinary sentences (several at once, or without a name), asks for the name, and tells the chat model."""

import tempfile
import time
import unittest
from pathlib import Path

from memory.profile import PlayerProfile, find_pets
from personality.llm import build_messages
from tests.test_brain import Base


class FindTests(unittest.TestCase):
    def test_ordinary_sentences(self):
        cases = {
            "ive got a dog called rex and hes 3": [("dog", "rex")],
            "my dog rex is mad": [("dog", "rex")],
            "my dogs name is rex": [("dog", "rex")],
            "we have two cats called milo and luna": [("cat", "milo"), ("cat", "luna")],
            "rex is my dog": [("dog", "rex")],
            "my cat milo keeps me company while i fly": [("cat", "milo")],
            "we have a cat named tilly and a dog called buddy": [("cat", "tilly"), ("dog", "buddy")],
            "my parrot called kevin says hello": [("parrot", "kevin")],
            "my dog rex is mad and i have a cat called luna": [("dog", "rex"), ("cat", "luna")],
            "i have a dog": [("dog", "")],
            "ive got two cats": [("cat", "")],
            "i have a dog and a cat": [("dog", ""), ("cat", "")],
        }
        for text, expected in cases.items():
            self.assertEqual(find_pets(text), expected, text)

    def test_chatter_is_not_a_pet(self):
        for text in ("my dog barked all night", "my dog sleeps all day", "my cat and my dog are best friends", "i have a dog that barks",
                     "my dog is so cute", "my dog died last week", "my cat is ill and i might lose her", "the dog next door barks"):
            names = [n for _k, n in find_pets(text) if n]
            self.assertEqual(names, [], text)
        self.assertEqual(find_pets("my dog died last week"), [])


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.profile = PlayerProfile(Path(self.dir.name) / "p.json")

    def test_several_pets_in_one_sentence(self):
        kind, values, new = self.profile.learn("we have two cats called milo and luna")
        self.assertEqual((kind, values["name"], new), ("pet", "Milo", True))
        self.assertEqual([e["name"] for e in self.profile.extra_pets], ["Luna"])
        self.assertEqual(sorted(p["name"] for p in self.profile.pets), ["luna", "milo"])

    def test_same_pet_twice_is_not_new(self):
        self.profile.learn("my dog is called rex")
        kind, values, new = self.profile.learn("ive got a dog called rex")
        self.assertFalse(new)

    def test_an_unnamed_pet_is_remembered_then_named(self):
        kind, values, new = self.profile.learn("i have a dog")
        self.assertEqual((kind, values["name"], new), ("pet", "", True))
        self.assertIsNotNone(self.profile.pending_pet)
        result = self.profile.learn("his name is rex")
        self.assertEqual(result[1]["name"], "Rex")
        self.assertEqual(self.profile.pets, [{"kind": "dog", "name": "rex"}])          # the unnamed one became rex

    def test_a_bare_name_answers_the_question_but_only_for_a_while(self):
        self.profile.learn("i have a cat")
        self.assertEqual(self.profile.learn("luna")[1]["name"], "Luna")
        self.profile.learn("i have a dog")
        self.profile.pending_pet = ("dog", time.monotonic() - 1000)
        self.assertIsNone(self.profile.learn("rex"))

    def test_a_bare_word_means_nothing_without_the_question(self):
        self.assertIsNone(self.profile.learn("rex"))

    def test_a_second_unnamed_dog_changes_nothing(self):
        self.profile.learn("i have a dog")
        self.assertFalse(self.profile.learn("i have a dog")[2])
        self.assertEqual(len(self.profile.pets), 1)

    def test_summary_and_mentions_cope_with_unnamed_pets(self):
        self.profile.learn("i have a dog")
        self.profile.learn("my cat is called milo")
        self.assertEqual(self.profile.summary_values()["pets"], "a dog and Milo the cat")
        self.assertEqual(self.profile.mentions("milo is asleep")[1]["name"], "Milo")
        self.assertIsNone(self.profile.mentions("the dog is asleep"))          # nothing to name

    def test_the_file_survives_a_restart(self):
        self.profile.learn("i have a dog and a cat called milo")
        again = PlayerProfile(Path(self.dir.name) / "p.json")
        self.assertEqual(sorted((p["kind"], p["name"]) for p in again.pets), [("cat", "milo"), ("dog", "")])


class ChatModelTests(unittest.TestCase):
    def test_pets_are_told_to_the_chat_model(self):
        messages = build_messages("hello there starling", pets=["Rex the dog", "a cat"])
        self.assertIn("Rex the dog, a cat", messages[0]["content"])

    def test_no_pets_no_sentence(self):
        self.assertNotIn("pets", build_messages("hello there starling")[0]["content"])


class InTheBrain(Base):
    def setUp(self):
        super().setUp()
        self.tmp2 = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp2.cleanup)
        self.profile = PlayerProfile(Path(self.tmp2.name) / "p.json")
        self.brain.profile = self.profile

    def test_a_natural_sentence_is_learned_and_said_back(self):
        reply = self.ask("i have got a dog called rex and he is three")
        self.assertIn("Rex", reply)
        self.assertEqual(self.profile.pets, [{"kind": "dog", "name": "rex"}])

    def test_two_pets_are_both_acknowledged(self):
        reply = self.ask("we have two cats called milo and luna")
        self.assertIn("Milo", reply)
        self.assertIn("Luna", reply)

    def test_an_unnamed_pet_makes_her_ask_and_the_answer_is_kept(self):
        reply = self.ask("i have a dog")
        self.assertIn("dog", reply)
        self.assertEqual(self.profile.pets, [{"kind": "dog", "name": ""}])
        reply = self.ask("his name is rex")
        self.assertIn("Rex", reply)
        self.assertEqual(self.profile.pets, [{"kind": "dog", "name": "rex"}])
        self.assertIn("Rex", self.ask("what are my pets called"))


if __name__ == "__main__":
    unittest.main()
