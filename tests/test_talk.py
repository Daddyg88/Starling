import random
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from core import paths
from core.event_bus import EventBus
from core.settings import Settings
from personality.chitchat import ChitChat, FREQUENCY
from personality.dialogue import DialogueManager
from personality.mood_engine import MoodEngine
from personality.smalltalk import SmallTalk, intent_for
from tests.test_chitchat import Speech
from tests.test_dialogue import real_dialogue


class IntentTests(unittest.TestCase):
    def test_small_talk_is_recognised(self):
        cases = {"how are you": "Talk_HowAreYou", "How are you doing today?": "Talk_HowAreYou", "tell me a joke": "Talk_Joke",
                 "talk to me": "Talk_Chat", "I'm bored": "Talk_Chat", "are you there": "Talk_Here", "hello": "Talk_Hello",
                 "Good morning, Starling": "Talk_Hello", "good night": "Talk_Goodnight", "I'm back": "Talk_Back",
                 "good job": "Talk_Compliment", "you're amazing": "Talk_Compliment", "I love you": "Talk_Love",
                 "what are you thinking": "Talk_Thinking", "what's your name": "Talk_Name"}
        for text, key in cases.items():
            self.assertEqual(intent_for(text), key, text)

    def test_commands_are_never_mistaken_for_chat(self):
        for text in ("open the galaxy map", "deploy landing gear", "request docking", "plot a route to Sol", "good", "target wingman 2",
                     "hello please open the cargo scoop", "how are you going to get there", "say something to the station"):
            self.assertIsNone(intent_for(text), text)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(Path(self.tmp.name) / "s.json").load()
        self.bus = EventBus()
        self.speech = Speech()
        self.dialogue = DialogueManager(paths.VOICEPACKS_DIR / "default", rng=random.Random(5)).load()
        self.t = [1000.0]
        self.state = SimpleNamespace(docked=False, in_supercruise=False, ship="python", system="Sol", station=None)
        self.chat = ChitChat(self.bus, self.speech, self.dialogue, self.settings, lambda: self.state, lambda: True,
                             clock=lambda: self.t[0], rng=random.Random(2))
        self.chat.attach()


class SmallTalkTests(Base):
    def setUp(self):
        super().setUp()
        self.mood = MoodEngine(self.bus, self.settings, save_path=Path(self.tmp.name) / "m.json", persist=False, clock=lambda: self.t[0])
        self.talk = SmallTalk(self.speech, self.dialogue, self.settings, chitchat=self.chat, mood=self.mood)

    def test_how_are_you_gets_a_spoken_answer(self):
        reply = self.talk.try_handle("how are you")
        self.assertTrue(reply)
        self.assertEqual(self.speech.said[0]["text"], reply)

    def test_not_small_talk_returns_none(self):
        self.assertIsNone(self.talk.try_handle("open the galaxy map"))
        self.assertEqual(self.speech.said, [])

    def test_kind_words_lift_her_mood_a_little(self):
        self.talk.try_handle("good job")
        self.assertGreater(self.mood.score, 0)

    def test_jokes_and_questions_do_not_change_mood(self):
        self.talk.try_handle("tell me a joke")
        self.talk.try_handle("how are you")
        self.assertEqual(self.mood.score, 0)

    def test_name_is_filled_in(self):
        reply = self.talk.try_handle("what's your name")
        self.assertNotIn("{name}", reply)
        self.assertIn("Starling", reply)

    def test_talk_to_me_chats_straight_away(self):
        reply = self.talk.try_handle("talk to me")
        self.assertTrue(reply)
        self.assertEqual(len(self.speech.said), 1)

    def test_can_be_switched_off(self):
        self.settings.set("smalltalk.enabled", False)
        self.assertIsNone(self.talk.try_handle("how are you"))

    def test_every_talk_key_has_lines(self):
        for key in ("Talk_HowAreYou", "Talk_Joke", "Talk_Chat", "Talk_Here", "Talk_Hello", "Talk_Goodnight", "Talk_Back",
                    "Talk_Compliment", "Talk_Love", "Talk_Thinking", "Talk_Name"):
            self.assertGreaterEqual(len(self.dialogue.pool(key, "", False, False)), 2, key)


class ChatterTests(Base):
    def test_lines_that_mention_things_are_only_used_when_known(self):
        self.state.ship, self.state.system = None, None
        for _ in range(60):
            text = self.chat._pick_text(1000.0, "", False)
            self.assertIsNotNone(text)
            self.assertNotIn("{", text)

    def test_context_counts_jumps_and_distance(self):
        for _ in range(4):
            self.bus.publish("FSDJump", {"JumpDist": 20.0, "StarSystem": "A"})
        self.t[0] += 25 * 60
        ctx = self.chat.context()
        self.assertEqual(ctx["jumps"], 4)
        self.assertEqual(ctx["distance"], 80)
        self.assertEqual(ctx["minutes"], 25)
        self.assertEqual(ctx["ship"], "Python")
        self.assertEqual(ctx["system"], "Sol")

    def test_flying_lines_use_real_values(self):
        for _ in range(5):
            self.bus.publish("FSDJump", {"JumpDist": 30.0, "StarSystem": "A"})
        self.t[0] += 30 * 60
        seen = {self.chat._pick_text(self.t[0], "", False) for _ in range(150)}
        self.assertTrue(any("Python" in s or "Sol" in s or "5 jumps" in s for s in seen))

    def test_chatty_is_the_liveliest(self):
        self.assertLess(FREQUENCY["chatty"][1], FREQUENCY["often"][1])
        self.assertLess(FREQUENCY["often"][1], FREQUENCY["normal"][1])

    def test_default_is_livelier_than_before(self):
        self.assertLessEqual(FREQUENCY["normal"][1], 360.0)

    def test_memory_can_be_mentioned(self):
        class Mem:
            def login_line(self):
                return "I was thinking about your longest jump."
        self.chat.memory = Mem()
        self.chat.rng = random.Random(0)
        texts = {self.chat._memory_text() for _ in range(40)}
        self.assertIn("I was thinking about your longest jump.", texts)

    def test_combat_never_talks_about_memories(self):
        class Mem:
            def login_line(self):
                return "MEMORY"
        self.chat.memory = Mem()
        self.bus.publish("CombatModeOn", {})
        self.t[0] += 5000
        for _ in range(10):
            self.chat.last_chat = self.chat.last_spoke = 0
            self.assertNotEqual(self.chat.tick(), "MEMORY")


class LongLineTests(unittest.TestCase):
    ALLOWED = {"StarSystem", "JumpDist", "StationName", "LandingPad", "ship", "system", "station", "jumps", "distance", "minutes", "name"}

    def test_placeholders_are_all_known(self):
        d = real_dialogue()
        for key, lines in d.lines.items():
            if not (key.startswith(("ChitChat", "Talk_")) or key in ("FSDJump", "Docked", "Undocked", "DockingGranted")):
                continue
            for line in lines:
                for field in re.findall(r"\{(\w+)", line.text):
                    self.assertIn(field, self.ALLOWED, "%s: %s" % (key, line.text))

    def test_everyday_events_now_have_full_sentence_variants(self):
        d = real_dialogue()
        for key in ("FSDJump", "Docked", "Undocked", "SupercruiseEntry", "SupercruiseExit", "Touchdown", "Liftoff", "FuelScoopComplete",
                    "DockingGranted", "ApproachBody", "NavRoute"):
            longer = [l for l in d.lines[key] if len(l.text) > 55]
            self.assertGreaterEqual(len(longer), 3, key)


if __name__ == "__main__":
    unittest.main()
