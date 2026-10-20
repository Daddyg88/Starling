import json
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core import paths
from core.settings import Settings
from personality.dialogue import DialogueManager
from personality.eoc import EOCTeller, same_person, speakable
from personality.smalltalk import SmallTalk
from tests.test_dialogue import FakeSpeech


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(Path(self.tmp.name) / "s.json").load()
        self.speech = FakeSpeech()
        self.dialogue = DialogueManager(paths.VOICEPACKS_DIR / "default", [paths.DIALOGUE_DIR / "core_lines.json"],
                                        rng=random.Random(2)).load()
        self.state = SimpleNamespace(commander="Someone Else")
        self.t = [100.0]
        self.eoc = EOCTeller(self.speech, self.dialogue, self.settings, state_provider=lambda: self.state,
                             clock=lambda: self.t[0], rng=random.Random(1))

    def said(self):
        return " ".join(str(x.get("text", x)) if isinstance(x, dict) else str(x) for x in self.speech.said)


class DataTests(Base):
    def test_all_nine_systems_are_known(self):
        titles = [s["title"] for s in self.eoc.data["systems"]]
        self.assertEqual(len(titles), 9)
        for name in ("Danforth", "Arcadia", "Black Legacy", "Baskerville Ring", "Payden's Haven", "Winter Station",
                     "Rhino Heaven", "Milliways", "Rancid Roquefort"):
            self.assertIn(name, titles)
        self.assertEqual(self.eoc.data["ceo"], ["Ben Can-Obi"])

    def test_names_and_codes(self):
        self.assertTrue(same_person("CMDR Ben Can-Obi", "ben can obi"))
        self.assertFalse(same_person("", ""))
        self.assertEqual(speakable("Wregoe JU-E c25-18"), "Wregoe J U, E, C 25, 18")
        self.assertEqual(speakable("HIP 49836"), "H I P 49836")

    def test_broken_file_is_survivable(self):
        bad = Path(self.tmp.name) / "bad.json"
        bad.write_text("{nope")
        teller = EOCTeller(self.speech, self.dialogue, self.settings, path=bad)
        self.assertIsNone(teller.try_handle("tell me about the east orion company"))

    def test_every_pool_line_formats(self):
        pack = json.load(open(paths.VOICEPACKS_DIR / "default" / "eoc.json", encoding="utf-8"))
        values = {"count": 9, "ceo": "A", "home": "B", "names": "C", "title": "D", "architect": "E"}
        for key, lines in pack.items():
            for item in lines:
                (item["text"] if isinstance(item, dict) else item).format(**values)


class AskingTests(Base):
    def test_overview_and_tour(self):
        self.assertTrue(self.eoc.try_handle("tell me about the east orion company"))
        self.assertIn("massive", self.said())
        self.assertIn("Ben Can-Obi", self.said())
        self.speech.said.clear()
        self.eoc.next()
        self.assertIn("Danforth", self.said())
        self.assertIn("Wregoe J U, E, C 25, 18", self.said())
        for _ in range(8):
            self.eoc.next()
        self.assertIn("Rancid Roquefort", self.said())
        self.eoc.next()
        self.assertIn("every company system", self.said())

    def test_ceo_you(self):
        self.state.commander = "CMDR Ben Can-Obi"
        self.eoc.try_handle("who is the ceo")
        self.assertIn("You", self.said())
        self.speech.said.clear()
        self.eoc.try_handle("tell me about the EOC")
        self.assertIn("you", self.said().lower())

    def test_ceo_someone_else(self):
        self.eoc.try_handle("who is the ceo of the east orion company")
        self.assertIn("Ben Can-Obi", self.said())

    def test_list(self):
        self.eoc.try_handle("which systems does the eoc own")
        self.assertIn("Milliways", self.said())
        self.assertIn("9 known", self.said())

    def test_one_system_by_name_station_or_architect(self):
        for text, expect in (("tell me about Arcadia", "Nyx Evera"), ("what is Milliways", "CplStump"),
                             ("tell me about the pensioner retreat", "Payden"), ("who is curd nerd", "blue cheese"),
                             ("tell me about winter station", "composites")):
            self.speech.said.clear()
            self.assertTrue(self.eoc.try_handle(text), text)
            self.assertIn(expect.lower(), self.said().lower(), text)

    def test_builder_is_recognised(self):
        self.state.commander = "Nyx Evera"
        self.eoc.try_handle("tell me about arcadia")
        self.assertIn("you", self.said().lower())

    def test_ordinary_sentences_are_left_alone(self):
        for text in ("plot a route to arcadia", "lower the landing gear", "what time is it", "tell me a joke", "who are you"):
            self.assertIsNone(self.eoc.try_handle(text), text)


class ThroughSmallTalk(Base):
    def test_company_questions_beat_the_back_story_and_more_continues(self):
        talk = SmallTalk(self.speech, self.dialogue, self.settings, eoc=self.eoc)
        talk.try_handle("tell me about the east orion company")
        self.assertIn("massive", self.said())
        self.speech.said.clear()
        talk.try_handle("tell me more")
        self.assertIn("Danforth", self.said())
        self.speech.said.clear()
        talk.try_handle("who is the ceo")
        self.assertIn("Ben Can-Obi", self.said())

    def test_who_are_you_still_tells_the_back_story(self):
        talk = SmallTalk(self.speech, self.dialogue, self.settings, eoc=self.eoc)
        self.assertTrue(talk.try_handle("who are you"))


if __name__ == "__main__":
    unittest.main()
