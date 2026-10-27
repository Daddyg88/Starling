"""Looking things up: off by default, topic words only, careful about what it accepts, remembers, can forget."""

import tempfile
import unittest
from pathlib import Path

from personality.knowledge import Knowledge
from personality.lookup import LearnedFacts, OnlineLookup, subject_of, tidy_extract
from tests.test_brain import Base


class FakeWiki:
    def __init__(self, offline=False):
        self.urls, self.offline = [], offline

    def __call__(self, url):
        self.urls.append(url)
        if self.offline:
            return None
        if "list=search" in url:
            if "quasar" in url:
                return {"query": {"search": [{"title": "Quasar"}]}}
            if "kardashev" in url.lower():
                return {"query": {"search": [{"title": "List of things"}, {"title": "Kardashev scale"}]}}
            if "mercury" in url:
                return {"query": {"search": [{"title": "Mercury"}]}}
            if "tallest" in url:
                return {"query": {"search": [{"title": "Banana"}]}}
            return {"query": {"search": []}}
        if "Quasar" in url:
            return {"type": "standard", "title": "Quasar",
                    "extract": "A quasar (/ˈkweɪzɑːr/) is an extremely luminous active galactic nucleus. It is powered by a black hole. More text here."}
        if "Kardashev" in url:
            return {"type": "standard", "title": "Kardashev scale", "extract": "The Kardashev scale is a method of measuring a civilization's level of technological advancement."}
        if "Mercury" in url:
            return {"type": "standard", "title": "Mercury", "extract": "Mercury may refer to: the planet, the element or the god."}
        return None


class Subjects(unittest.TestCase):
    def test_what_is_questions(self):
        self.assertEqual(subject_of("what is a quasar"), ("def", "quasar"))
        self.assertEqual(subject_of("who was ada lovelace"), ("def", "ada lovelace"))
        self.assertEqual(subject_of("tell me about the hubble constant"), ("def", "hubble constant"))
        self.assertEqual(subject_of("how tall is the eiffel tower"), ("detail", "eiffel tower"))
        self.assertEqual(subject_of("who invented the zip"), ("detail", "zip"))

    def test_personal_and_worrying_questions_are_never_sent(self):
        for said in ("what is my name", "who are you", "what is your favourite colour", "what is wrong with me", "what is sex",
                     "what is going on", "how do i kill myself", "what is it", "what are we doing today starling",
                     "what is the best way to build a bomb", "what is a very long thing about nothing in particular at all"):
            self.assertIsNone(subject_of(said), said)

    def test_extract_cleaning(self):
        self.assertEqual(tidy_extract("A quasar (/kweɪ/) is a bright thing [1]. It is far away. Third."), "A quasar is a bright thing. It is far away.")
        self.assertIsNone(tidy_extract("See https://example.com for more information please"))


class Lookup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "learned.json"

    def make(self, wiki, enabled=True):
        from core.settings import Settings
        settings = Settings(Path(self.tmp.name) / "s.json").load()
        settings.set("brain.lookup", enabled)
        self.now = [100.0]
        return OnlineLookup(settings, LearnedFacts(self.path), fetch=wiki, clock=lambda: self.now[0], background=False)

    def test_off_by_default(self):
        from core.settings import Settings
        self.assertFalse(Settings(Path(self.tmp.name) / "x.json").load().get("brain.lookup", False))
        wiki = FakeWiki()
        self.assertIsNone(self.make(wiki, enabled=False).should_try("what is a quasar"))
        self.assertEqual(wiki.urls, [])

    def test_finds_cleans_and_remembers(self):
        wiki = FakeWiki()
        look = self.make(wiki)
        kind, subject = look.should_try("what is a quasar")
        title, text = look.find(kind, subject)
        self.assertEqual(title, "Quasar")
        self.assertNotIn("(", text)
        self.assertLessEqual(text.count("."), 2)
        self.assertTrue(all("quasar" in u or "Quasar" in u for u in wiki.urls))     # only the topic is sent
        self.assertNotIn("what", wiki.urls[0].lower().replace("whatis", ""))
        again = LearnedFacts(self.path)                                              # survives a restart
        self.assertIn("def:quasar", again.items)
        self.assertEqual(self.make(FakeWiki(offline=True)).known("tell me about quasars")[0], "Quasar")

    def test_skips_lists_and_disambiguation_and_unrelated_titles(self):
        look = self.make(FakeWiki())
        self.assertEqual(look.find("def", "kardashev scale")[0], "Kardashev scale")
        self.assertIsNone(look.find("def", "mercury"))
        self.assertIsNone(look.find("detail", "tallest thing"))

    def test_offline_and_rate_limit_and_retry(self):
        look = self.make(FakeWiki(offline=True))
        kind, subject = look.should_try("what is a quasar")
        self.assertEqual(look.find(kind, subject), "offline")
        self.assertIsNone(look.should_try("what is a pulsar"))            # one lookup every few seconds
        self.now[0] += 20
        self.assertIsNotNone(look.should_try("what is a pulsar"))

    def test_nothing_found_is_not_retried_for_a_while(self):
        look = self.make(FakeWiki())
        kind, subject = look.should_try("what is a flurbo")
        self.assertIsNone(look.find(kind, subject))
        self.now[0] += 20
        self.assertIsNone(look.should_try("what is a flurbo"))
        self.now[0] += 700
        self.assertIsNotNone(look.should_try("what is a flurbo"))

    def test_forget(self):
        look = self.make(FakeWiki())
        look.find("def", "quasar")
        self.assertEqual(look.handle_forget("forget everything you looked up"), 1)
        self.assertFalse(self.path.exists())
        self.assertIsNone(look.handle_forget("what is a quasar"))


class InTheBrain(Base):
    def setUp(self):
        super().setUp()
        self.brain.knowledge = Knowledge()
        self.path = Path(self.tmp.name) / "learned.json"
        self.wiki = FakeWiki()
        self.look = OnlineLookup(self.settings, LearnedFacts(self.path), fetch=self.wiki, clock=self.clock, background=False)
        self.brain.lookup = self.look

    def test_unknown_question_is_looked_up_only_when_switched_on(self):
        self.assertNotIn("Wikipedia", self.ask("what is a quasar") or "")
        self.assertEqual(self.wiki.urls, [])
        self.settings.set("brain.lookup", True)
        reply = self.ask("what is a quasar")
        self.assertIn("luminous", reply)
        self.assertTrue(self.speech.said)

    def test_second_time_comes_from_memory_without_the_internet(self):
        self.settings.set("brain.lookup", True)
        self.ask("what is a quasar")
        count = len(self.wiki.urls)
        self.settings.set("brain.lookup", False)
        self.assertIn("luminous", self.ask("tell me about quasars"))
        self.assertEqual(len(self.wiki.urls), count)

    def test_not_found_and_offline_and_forget(self):
        self.settings.set("brain.lookup", True)
        style = self.brain.knowledge.style
        self.assertIn(self.ask("what is a flurbo"), [t for t in style["not_found"]])
        self.look._last = -1e9
        self.look.fetch = FakeWiki(offline=True)
        self.assertIn(self.ask("what is a pulsar"), style["offline"])
        self.look.fetch = FakeWiki()
        self.look._last = -1e9
        self.ask("what is a quasar")
        self.assertTrue(self.look.learned.items)
        self.assertIn(self.ask("forget everything you looked up"), style["forgot"])
        self.assertFalse(self.look.learned.items)

    def test_known_facts_never_hit_the_internet(self):
        self.settings.set("brain.lookup", True)
        self.assertIn("Paris", self.ask("what is the capital of france"))
        self.assertEqual(self.wiki.urls, [])

    def test_chat_and_personal_questions_are_not_sent(self):
        self.settings.set("brain.lookup", True)
        self.ask("what is my name")
        self.ask("i had a pizza for dinner and it was lovely")
        self.assertEqual(self.wiki.urls, [])


if __name__ == "__main__":
    unittest.main()


class TidyExtract(unittest.TestCase):
    """'what is tritium' came back empty on her PC: the long summary had too many digits, and a bracket inside a bracket left junk."""

    TRITIUM = ("Tritium (from Ancient Greek τρίτος (trítos) 'third') or hydrogen-3 (symbol T or ³H) is a rare and radioactive isotope of "
               "hydrogen with a half-life of ~12.3 years. The tritium nucleus (t, sometimes called a triton) contains one proton and two "
               "neutrons, whereas the nucleus of the common isotope hydrogen-1 (protium) contains one proton and that of hydrogen-2 "
               "(deuterium) contains one proton and one neutron.")

    def test_a_summary_full_of_numbers_still_gives_its_first_sentence(self):
        self.assertEqual(tidy_extract(self.TRITIUM),
                         "Tritium or hydrogen-3 is a rare and radioactive isotope of hydrogen with a half-life of 12.3 years.")

    def test_brackets_inside_brackets_are_removed(self):
        self.assertEqual(tidy_extract("Zorp (from the Greek (zorpos) word for fish) is a fish."), "Zorp is a fish.")

    def test_a_short_first_sentence_gets_the_second_one_too(self):
        self.assertEqual(tidy_extract("A quasar is a bright thing. It is far away and very old."), "A quasar is a bright thing. It is far away and very old.")
