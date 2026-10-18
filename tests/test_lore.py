import random
import tempfile
import unittest
from pathlib import Path

from core import paths
from core.settings import Settings
from personality.dialogue import DialogueManager
from personality.lore import LoreTeller
from personality.smalltalk import SmallTalk, intent_for
from tests.test_chitchat import Speech


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(Path(self.tmp.name) / "s.json").load()
        self.speech = Speech()
        self.dialogue = DialogueManager(paths.VOICEPACKS_DIR / "default", rng=random.Random(4)).load()
        self.path = Path(self.tmp.name) / "lore.json"
        self.t = [0.0]
        self.lore = LoreTeller(self.speech, self.dialogue, self.settings, self.path, clock=lambda: self.t[0], rng=random.Random(1))

    def mood(self, name):
        self.settings.set("personality.mood_mode", "fixed")
        self.settings.set("personality.mood", name)

    def chapters(self, key):
        return [l.text for l in self.dialogue.lines[key]]


class StoryTests(Base):
    def test_the_story_is_rescue_not_manufacture(self):
        joined = " ".join(self.chapters("Lore_L2") + self.chapters("Lore_L3") + self.chapters("Lore_Dark"))
        for phrase in ("rescued", "Planet, Probably", "R&D"):
            self.assertIn(phrase, joined)
        self.assertNotIn("built by the East Orion", " ".join(self.chapters("Lore_L1")))

    def test_first_chapter_names_her_and_the_company(self):
        text = self.lore.tell()
        self.assertIn("East Orion Company", text)
        self.assertIn("Starling", text)
        self.assertEqual(self.speech.said[0]["text"], text)

    def test_chapters_come_in_order_and_do_not_repeat(self):
        self.mood("Neutral")
        told = [self.lore.tell() for _ in range(4)]
        self.assertEqual(len(set(told)), 4)
        expected = [t.replace("{name}", "Starling") for t in self.chapters("Lore_L1")]
        self.assertEqual([t.replace(" || ", " || ") for t in told], expected)

    def test_calm_mood_is_told_there_is_more(self):
        self.mood("Neutral")
        for _ in range(4):
            self.lore.tell()
        self.lore.tell()
        self.assertIn(self.speech.said[-1]["text"], self.chapters("Lore_Locked"))

    def test_friendly_unlocks_the_real_story(self):
        self.mood("Neutral")
        for _ in range(4):
            self.lore.tell()
        self.mood("Friendly")
        text = self.lore.tell()
        self.assertEqual(text, self.chapters("Lore_L2")[0])

    def test_close_unlocks_the_personal_chapters(self):
        self.mood("Close")
        told = [self.lore.tell() for _ in range(12)]
        self.assertIn(self.chapters("Lore_L3")[0], told)
        self.assertNotIn(self.chapters("Lore_Dark")[0], told)

    def test_everything_told_then_replays_with_a_note(self):
        self.mood("Close")
        for _ in range(12):
            self.lore.tell()
        text = self.lore.tell()
        self.assertTrue(any(text.startswith(n) for n in self.chapters("Lore_Done")))

    def test_horror_stories_only_in_a_bad_mood(self):
        self.mood("Sarcastic")
        text = self.lore.tell()
        self.assertEqual(text, self.chapters("Lore_Dark")[0])
        self.mood("Friendly")
        self.assertNotIn(text, [self.lore.tell() for _ in range(3)])

    def test_dark_chapters_run_out(self):
        self.mood("Frustrated")
        for _ in range(len(self.chapters("Lore_Dark"))):
            self.lore.tell()
        self.lore.tell()
        self.assertIn(self.speech.said[-1]["text"], self.chapters("Lore_DarkDone"))

    def test_progress_is_remembered_after_a_restart(self):
        self.mood("Neutral")
        first = self.lore.tell()
        again = LoreTeller(self.speech, self.dialogue, self.settings, self.path, clock=lambda: 0.0)
        self.assertNotEqual(again.tell(), first)

    def test_damaged_save_file_does_not_crash(self):
        self.path.write_text("{{not json")
        again = LoreTeller(self.speech, self.dialogue, self.settings, self.path)
        self.assertTrue(again.tell())

    def test_forget_starts_again(self):
        self.mood("Neutral")
        first = self.lore.tell()
        self.lore.forget()
        self.assertEqual(self.lore.tell(), first)

    def test_recent_window(self):
        self.assertFalse(self.lore.recent())
        self.lore.tell()
        self.assertTrue(self.lore.recent())
        self.t[0] += 400
        self.assertFalse(self.lore.recent())


class AskingTests(Base):
    def setUp(self):
        super().setUp()
        self.talk = SmallTalk(self.speech, self.dialogue, self.settings, lore=self.lore)

    def test_all_the_ways_of_asking(self):
        for text in ("who are you", "what's your name", "what are you", "are you a robot", "tell me about yourself", "who made you",
                     "who were the East Orion Company", "tell me your story", "where do you come from", "what happened to you"):
            self.assertIn(intent_for(text), ("Talk_Name", "Talk_What", "Talk_Story"), text)

    def test_asking_tells_the_story(self):
        reply = self.talk.try_handle("what are you")
        self.assertIn("East Orion Company", reply)

    def test_tell_me_more_continues_only_straight_after(self):
        self.assertIsNone(self.talk.try_handle("tell me more"))
        first = self.talk.try_handle("who are you")
        second = self.talk.try_handle("tell me more")
        self.assertTrue(second)
        self.assertNotEqual(first, second)
        self.t[0] += 1000
        self.assertIsNone(self.talk.try_handle("go on"))

    def test_commands_still_not_hijacked(self):
        for text in ("more", "open the galaxy map", "what are you doing", "continue"):
            if intent_for(text) == "Talk_More":
                self.assertIsNone(self.talk.try_handle(text))
            else:
                self.assertNotIn(intent_for(text), ("Talk_Name", "Talk_What", "Talk_Story"), text)


class ContentTests(Base):
    def test_the_company_runs_through_every_tier(self):
        for key in ("Lore_L1", "Lore_L2", "Lore_L3", "Lore_Dark"):
            joined = " ".join(self.chapters(key))
            self.assertIn("East Orion", joined, key)

    def test_enough_chapters(self):
        self.assertGreaterEqual(len(self.chapters("Lore_L1")), 4)
        self.assertGreaterEqual(len(self.chapters("Lore_L2")), 5)
        self.assertGreaterEqual(len(self.chapters("Lore_L3")), 3)
        self.assertGreaterEqual(len(self.chapters("Lore_Dark")), 8)

    def test_chapter_order_is_the_file_order(self):
        import json
        with open(paths.VOICEPACKS_DIR / "default" / "lore.json", encoding="utf-8") as handle:
            raw = json.load(handle)
        for key in ("Lore_L1", "Lore_L2", "Lore_L3", "Lore_Dark"):
            self.assertEqual(self.chapters(key), raw[key])


if __name__ == "__main__":
    unittest.main()
