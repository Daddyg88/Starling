"""What she knows: facts, capitals, languages, sums and conversions - exact, never invented, never hijacking chat."""

import json
import unittest

from core import paths
from personality.knowledge import Knowledge, convert, digits, maths
from tests.test_brain import Base

LIBRARY = Knowledge()


class Data(unittest.TestCase):
    def test_every_entry_is_complete(self):
        for path in sorted((paths.CONFIG_DIR / "knowledge").glob("*.json")):
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            for entry in data.get("entries", []):
                self.assertTrue(entry["a"].strip(), path.name)
                self.assertTrue(entry["k"] and all(alt and all(isinstance(w, str) for w in alt) for alt in entry["k"]), entry["a"])
        self.assertGreater(len(LIBRARY.entries), 200)
        self.assertGreater(len(LIBRARY.capitals), 150)

    def test_no_two_entries_share_the_same_key_words(self):
        seen = {}
        for alternatives, answer in LIBRARY.entries:
            for alt in alternatives:
                if alt in seen and seen[alt] != answer:
                    self.fail("%s is used by two answers: %r and %r" % (sorted(alt), seen[alt], answer))
                seen[alt] = answer

    def test_every_language_has_every_word(self):
        for name, words in LIBRARY.languages.items():
            self.assertEqual(len(words), len(LIBRARY.lang_words), name)


class Facts(unittest.TestCase):
    def check(self, question, expect):
        hit = LIBRARY.lookup(question)
        self.assertIsNotNone(hit, question)
        self.assertIn(expect, str(hit[1]), question)

    def test_questions_in_different_wordings(self):
        for question, expect in (
                ("what is the capital of germany", "Berlin"), ("whats the capital of the usa", "Washington"),
                ("capital of japan", "Tokyo"), ("do you know the capital city of australia", "Canberra"),
                ("paris is the capital of which country", "France"),
                ("how do you say thank you in german", "danke"), ("how do i say hello in japanese", "konnichiwa"),
                ("what is goodbye in spanish", "adios"),
                ("how fast does light travel", "ninety nine thousand"), ("how many moons does mars have", "Phobos"),
                ("what is the centre of the galaxy called", "Sagittarius"), ("what is the center of the galaxy called", "Sagittarius"),
                ("tell me about beagle point", "edge"), ("what is a neutron star", "collapsed"),
                ("how does neutron boosting work", "four times"), ("what stars can i scoop from", "Oh Be A Fine Guy"),
                ("who invented the telephone", "Bell"), ("what year did world war two start", "1939"),
                ("when did world war one start", "1914"), ("how many bones are in the human body", "six bones"),
                ("how many seconds in a minute", "Sixty"), ("how far is the moon", "eighty four thousand"), ("what is the biggest planet", "Jupiter")):
            self.check(question, expect)

    def test_chat_is_never_mistaken_for_a_question(self):
        for said in ("i had pizza in paris last night", "euro truck simulator is fun", "i love the colonia system a lot",
                     "my dog chased the moon last night while we were walking", "the sun was out today and it was lovely",
                     "honk", "i met a german guy who said danke", "i have two cats", "coffee", "lets go in well"):
            self.assertIsNone(LIBRARY.lookup(said), said)

    def test_she_does_not_know_what_she_does_not_know(self):
        for said in ("what is the capital of narnia", "who will win the election", "what is the weather today",
                     "what is the price of bitcoin", "who is the prime minister"):
            self.assertIsNone(LIBRARY.lookup(said), said)


class Sums(unittest.TestCase):
    def test_sums(self):
        for said, expect in (("what is 12 times 7", "84"), ("whats 15 plus 27", "42"), ("what is twenty percent of 150", "30"),
                             ("what is the square root of 144", "12"), ("what is 5 squared", "25"), ("what is half of 90", "45"),
                             ("what is 7 x 8", "56"), ("how much is 100 minus 37", "63"), ("what is twelve times seven", "84"),
                             ("what is 10 divided by 4", "2.5"), ("what is 3 + 4", "7")):
            result = maths(said)
            self.assertIsNotNone(result, said)
            self.assertTrue(result[0].endswith(expect), (said, result))

    def test_divide_by_zero(self):
        self.assertEqual(maths("what is 10 divided by 0"), (None, "zero"))

    def test_game_talk_with_numbers_is_not_a_sum(self):
        for said in ("i did 3 jumps", "jump 2-3 times", "set speed to 75", "i have 2 cats and 3 dogs", "plot a route 3 jumps away",
                     "my score was 5 x 10"):
            self.assertIsNone(maths(said), said)

    def test_number_words(self):
        self.assertEqual(digits("twenty five times three"), "25 times 3")

    def test_conversions(self):
        for said, expect in (("convert 20 celsius to fahrenheit", "68 degrees Fahrenheit"), ("how many miles in 10 km", "6.214 miles"),
                             ("what is 100 km in miles", "62.14 miles"), ("how many feet in 2 metres", "6.562 feet"),
                             ("what is 0 celsius in kelvin", "273.1 kelvin"), ("convert 5 kilograms to pounds", "11.02 pounds")):
            result = convert(said)
            self.assertIsNotNone(result, said)
            self.assertTrue(result.endswith(expect), (said, result))
        self.assertIsNone(convert("convert 5 kilograms to miles"))


class InTheBrain(Base):
    def setUp(self):
        super().setUp()
        self.brain.knowledge = LIBRARY

    def test_she_answers_and_speaks(self):
        reply = self.ask("what is the capital of france")
        self.assertIn("Paris", reply)
        self.assertTrue(self.speech.said)
        self.assertIn("84", self.ask("what is 12 times 7"))
        self.assertIn("miles", self.ask("how many miles in 10 km"))

    def test_switch_off(self):
        self.settings.set("brain.knowledge", False)
        self.assertNotIn("Paris", self.ask("what is the capital of france") or "")

    def test_chat_still_works_and_facts_do_not_steal_commands(self):
        self.assertTrue(self.ask("i had a pizza for dinner and it was lovely"))
        self.assertIsNone(self.brain.knowledge.lookup("lower the landing gear"))

    def test_not_when_not_addressed(self):
        self.assertIsNone(self.ask("what is the capital of france", deliberate=False))


if __name__ == "__main__":
    unittest.main()
