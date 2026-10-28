"""0.76.0: fixes from a real log (wrong facts, wrong look-up pages, name, jokes, suggestions, greetings) and the Elite ship wiki."""
import tempfile
import unittest
from pathlib import Path

from core import ships as ship_table
from personality.knowledge import Knowledge
from personality.lookup import FANDOM, HOST, LearnedFacts, OnlineLookup, covers, norm_ship, ship_in
from personality.people import People
from personality.smalltalk import intent_for
from tests.test_brain import Base as BrainBase


def fake_fetch(url):
    """A pretend Wikipedia and Elite wiki."""
    if url.startswith(HOST) and "list=search" in url:
        if "green" in url:
            return {"query": {"search": [{"title": "Giant squid"}]}}
        return {"query": {"search": [{"title": "Quasar"}]}}
    if url.startswith(HOST) and "page/summary" in url:
        if "Giant" in url:
            return {"type": "standard", "title": "Giant squid", "extract": "The giant squid is a species of deep-ocean dwelling squid."}
        return {"type": "standard", "title": "Quasar", "extract": "A quasar is an extremely luminous active galactic nucleus powered by a black hole."}
    if url.startswith(FANDOM) and "list=search" in url:
        return {"query": {"search": [{"title": "Category:Ships"}, {"title": "Anaconda"}]}}
    if url.startswith(FANDOM) and "prop=extracts" in url:
        return {"query": {"pages": {"1": {"title": "Anaconda", "extract": "The Anaconda is a large multipurpose ship built by Faulcon DeLacy. It has the longest jump range of the big ships."}}}}
    return None


class ShipNameTests(unittest.TestCase):
    def test_different_ways_of_saying_a_ship(self):
        self.assertEqual(norm_ship("Cobra Mk III"), "cobra mark 3")
        self.assertEqual(norm_ship("cobra mark three"), "cobra mark 3")
        self.assertEqual(norm_ship("Fer-de-Lance"), "fer de lance")
        names = sorted(set(ship_table.known().values()))
        self.assertEqual(ship_in("tell me about the anaconda", names), "Anaconda")
        self.assertEqual(ship_in("how fast is the cobra mk 3", names), "Cobra Mark 3")
        self.assertEqual(ship_in("what is the fer de lance", names), "Fer-de-Lance")
        self.assertEqual(ship_in("what is the capital of peru", names), None)
        self.assertEqual(ship_in("python mark two jump range", names), "Python Mark 2")           # the longer name wins


class LookupTests(unittest.TestCase):
    def setUp(self):
        from core.settings import Settings
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(Path(self.tmp.name) / "s.json").load()
        self.settings.set("brain.lookup", True)
        self.look = OnlineLookup(self.settings, LearnedFacts(Path(self.tmp.name) / "l.json"), fetch=fake_fetch, background=False,
                                 ships=lambda: sorted(set(ship_table.known().values())))

    def test_a_page_that_does_not_mention_the_subject_is_refused(self):
        self.assertFalse(covers({"green", "gas", "giant"}, "Giant squid", "The giant squid is a species of deep-ocean dwelling squid."))
        self.assertIsNone(self.look.find("def", "green gas giant"))
        self.assertEqual(self.look.find("def", "quasar")[0], "Quasar")

    def test_ship_questions_use_the_elite_wiki_and_are_remembered(self):
        self.assertEqual(self.look.ship_subject("tell me about the anaconda"), ("ship", "Anaconda"))
        self.assertIsNone(self.look.ship_subject("my anaconda is brilliant"))                 # not a question
        title, text = self.look.find("ship", "Anaconda")
        self.assertEqual(title, "Anaconda")
        self.assertIn("Faulcon DeLacy", text)
        self.assertIn("Faulcon", self.look.known("what is the anaconda")[1])                  # saved for next time, works offline

    def test_wiki_unreachable_means_offline_not_a_guess(self):
        self.look.fetch = lambda url: None
        self.assertEqual(self.look.find("ship", "Anaconda"), "offline")


class BrainFixesTests(BrainBase):
    def setUp(self):
        super().setUp()
        self.brain.knowledge = Knowledge()
        self.brain.people = People(Path(self.tmp.name) / "people.json")
        from core.settings import Settings
        self.settings.set("brain.lookup", True)
        self.brain.lookup = OnlineLookup(self.settings, LearnedFacts(Path(self.tmp.name) / "l.json"), fetch=fake_fetch, background=False,
                                         ships=lambda: sorted(set(ship_table.known().values())))

    def said(self):
        return str(self.speech.said[-1]["text"])

    def test_facts_are_not_guessed_from_part_of_the_question(self):
        self.assertTrue(self.ask("what is the nearest star to our solar system"))
        self.assertIn("Alpha Centauri", self.said())
        self.assertTrue(self.ask("how many dwarf planets are there in our solar system"))
        self.assertIn("five", self.said())
        self.assertNotIn("eight planets", self.said())

    def test_tell_me_about_looks_it_up(self):
        self.assertTrue(self.ask("tell me about quasars"))
        self.assertIn("luminous", self.said())

    def test_a_green_gas_giant_is_not_a_squid(self):
        self.ask("what is a green gas giant")
        self.assertNotIn("squid", self.said())

    def test_ship_question_gets_the_wiki(self):
        self.assertTrue(self.ask("tell me about the anaconda"))
        self.assertIn("Faulcon", self.said())

    def test_plain_name_question_gives_the_name_not_the_story(self):
        self.assertEqual(intent_for("what is your name"), "Talk_Name")

    def test_another_joke_is_a_joke(self):
        for text in ("tell me another joke", "tell me another", "got another joke"):
            self.assertEqual(intent_for(text), "Talk_Joke", text)

    def test_what_shall_we_do_gets_a_suggestion(self):
        for text in ("what shall we do today", "what are we doing today", "where shall we go today", "what would you like to do today"):
            self.speech.said.clear()
            self.assertTrue(self.ask(text), text)
            self.assertNotIn("can't answer", self.said().lower(), text)

    def test_say_hello_to_my_wife_marie(self):
        self.assertTrue(self.ask("Say hello to my wife, Marie."))
        self.assertIn("Marie", self.said())
        self.assertEqual(self.brain.people.items["marie"]["relation"], "wife")
        self.assertTrue(self.ask("Say hello to my wife."))
        self.assertIn("Marie", self.said())                                  # she remembers who the wife is

    def test_do_you_like_it_never_says_just_it(self):
        self.speech.said.clear()
        self.ask("do you like it")
        self.assertFalse(self.speech.said and self.said().startswith("it?"))


if __name__ == "__main__":
    unittest.main()


class SentenceSplitTests(unittest.TestCase):
    def test_long_answers_are_made_a_sentence_at_a_time(self):
        from tts.kokoro_tts import split_sentences
        short = "Good question."
        self.assertEqual(split_sentences(short), [short])
        long_text = "Good question. There are 195 countries recognised in the world today: 193 United Nations members plus two observer states. That is all."
        parts = split_sentences(long_text)
        self.assertGreaterEqual(len(parts), 2)
        self.assertEqual(" ".join(parts), long_text)                       # nothing lost, nothing added
        self.assertTrue(all(len(p) >= 25 for p in parts[:-1]))              # no tiny first piece


class WikiFallbackTests(unittest.TestCase):
    def test_reads_the_page_html_when_the_wiki_has_no_extracts(self):
        from personality.lookup import first_paragraph
        page = ("<aside class='infobox'><p>Manufacturer: Faulcon DeLacy and a lot of other infobox words here</p></aside>"
                "<p>\n</p><p>The <b>Python</b> is a medium multipurpose ship built by Faulcon DeLacy &amp; popular with traders.</p>")
        self.assertIn("Faulcon DeLacy & popular", first_paragraph(page))
        self.assertNotIn("infobox", first_paragraph(page))
        self.assertIsNone(first_paragraph("<p>short</p>"))

    def test_ship_found_through_the_html_fallback(self):
        from core.settings import Settings
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)

        def fetch(url):
            if "list=search" in url:
                return {"query": {"search": [{"title": "Python"}]}}
            if "action=parse" in url:
                return {"parse": {"text": {"*": "<p>The Python is a medium multipurpose ship built by Faulcon DeLacy and loved by traders.</p>"}}}
            return {"query": {"pages": {"-1": {"missing": ""}}}}                # no extracts, no abstract: the older ways fail

        settings = Settings(Path(tmp.name) / "s.json").load()
        look = OnlineLookup(settings, LearnedFacts(Path(tmp.name) / "l.json"), fetch=fetch, background=False)
        self.assertIn("Faulcon", look.find("ship", "Python")[1])
