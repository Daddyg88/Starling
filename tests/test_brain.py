import random
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from control.matcher import Matcher
from core import paths
from core.settings import Settings
from personality.brain import Brain, load_intents
from personality.dialogue import DialogueManager
from tests.test_dialogue import FakeSpeech


class Facts:
    def next(self, topic="all"):
        return "A neutron star can spin hundreds of times a second."


class Clock:
    now = 1000.0

    def __call__(self):
        return self.now


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(Path(self.tmp.name) / "s.json").load()
        self.speech = FakeSpeech()
        self.dialogue = DialogueManager(paths.VOICEPACKS_DIR / "default", [paths.DIALOGUE_DIR / "core_lines.json"],
                                        rng=random.Random(3)).load()
        self.state = SimpleNamespace(ship="python", ship_name="Betsy", system="Sol", station=None, docked=False, in_supercruise=False,
                                     hull_health=1.0, shields_up=True, wanted=False, commander="Dave", status_flags=0)
        self.clock = Clock()
        self.brain = Brain(self.speech, self.dialogue, self.settings, state_provider=lambda: self.state, facts=Facts(),
                           clock=self.clock, rng=random.Random(4), now=lambda: datetime(2026, 10, 19, 21, 50))

    def ask(self, text, deliberate=True):
        return self.brain.try_handle(text, deliberate=deliberate)

    def topic(self):
        return self.brain.topic[0] if self.brain.topic else None


class DataTests(Base):
    def test_patterns_all_compile_and_every_intent_has_answers(self):
        intents = load_intents()
        self.assertGreater(len(intents), 70)
        special = {"Brain_Why", "Brain_More", "Brain_You", "Brain_Really", "Brain_RiddleReveal", "Brain_Riddle", "Brain_Fact",
                   "Brain_Opinion", "Brain_Suggest", "Brain_Status", "Brain_Wanted", "Brain_Time", "Brain_Date",
                   "Brain_SellPrice", "Brain_BuyPrice", "Brain_Mined", "Brain_Merit"}
        for item, _patterns in intents:
            key = item["key"]
            if key in special:
                continue
            self.assertTrue(self.dialogue.pool(key, "", True, False), key)

    def test_placeholders_only_use_known_fields(self):
        known = {"system", "station", "ship", "shipname", "commander", "minutes", "jumps", "distance", "hull", "shields",
                 "time", "period", "date", "result", "sides", "low", "high", "answer", "topic", "total", "best_text"}
        for key, lines in self.dialogue.lines.items():
            if not key.startswith("Brain_"):
                continue
            for line in lines:
                for name in re.findall(r"\{(\w+)\}", line.text):
                    self.assertIn(name, known, "%s: %s" % (key, line.text))

    def test_follow_up_pools_exist(self):
        for key in ("Brain_WhyGeneric", "Brain_MoreGeneric", "Brain_YouGeneric", "Brain_ReallyGeneric", "Brain_Status_Low",
                    "Brain_Suggest_Docked", "Brain_Wanted_Yes", "Brain_Wanted_No", "Brain_RiddleRight", "Brain_FactIntro"):
            self.assertTrue(self.dialogue.pool(key, "", True, False), key)

    def test_plenty_of_material(self):
        total = sum(len(v) for k, v in self.dialogue.lines.items() if k.startswith("Brain_"))
        self.assertGreater(total, 600)


class RecognitionTests(Base):
    def test_sentences_find_the_right_topic(self):
        cases = {
            "what's your favourite colour": "Brain_FavColour", "Starling, do you dream?": "Brain_Dream",
            "are you scared of anything": "Brain_Scared", "do you like me": "Brain_LikeMe",
            "do you like fighting": "Brain_LikeCombat", "what do you think of the Thargoids": "Brain_Thargoids",
            "what's the meaning of life": "Brain_Meaning", "how old are you": "Brain_Age", "roast me": "Brain_Roast",
            "write me a poem": "Brain_Poem", "tell me a story": "Brain_Story", "tell my fortune": "Brain_Fortune",
            "say hello to chat": "Brain_StreamHello", "thank you chat": "Brain_StreamThanks", "say goodbye to chat": "Brain_StreamBye",
            "what can you do": "Brain_ShowOff", "what's new": "Brain_WhatsNew", "I'm tired": "Brain_Tired", "cheer me up": "Brain_CheerUp",
            "flip a coin": "Brain_Coin", "roll a dice": "Brain_Dice", "pick a number": "Brain_Number", "give me a nickname": "Brain_Nickname",
            "that was close": "Brain_CloseCall", "wow": "Brain_Wow", "lol": "Brain_Funny", "you're useless": "Brain_Insulted",
            "give me a pickup line": "Brain_PickUp", "tell me a secret": "Brain_Secret", "would you rather": "Brain_WouldYouRather",
            "should I buy a Python": "Brain_EightBall", "what do you think about pulse lasers": "Brain_Opinion",
            "I'm sorry": "Brain_Sorry", "what's the best ship": "Brain_FavShip", "do you get lonely": "Brain_Lonely",
        }
        for text, key in cases.items():
            self.brain.topic = None
            self.assertIsNotNone(self.ask(text), text)
            self.assertEqual(self.topic(), key, text)

    def test_every_answer_is_spoken_once(self):
        self.ask("what's your favourite colour")
        self.assertEqual(len(self.speech.said), 1)
        self.assertEqual(self.speech.said[0]["event_name"], "brain")

    def test_unknown_things_are_left_alone(self):
        for text in ("open the galaxy map", "blah blah", "", "lower the landing gear"):
            self.assertIsNone(self.ask(text), text)
        self.assertEqual(self.speech.said, [])

    def test_not_for_her_means_silence(self):
        self.assertIsNone(self.ask("what's your favourite colour", deliberate=False))
        self.assertEqual(self.speech.said, [])

    def test_can_be_switched_off(self):
        self.settings.set("brain.enabled", False)
        self.assertIsNone(self.ask("what's your favourite colour"))

    def test_commands_are_not_stolen(self):
        # The runner only asks the brain when the matcher found nothing, so a real command can never reach it.
        matcher = Matcher()
        for text in ("lower the landing gear", "open the galaxy map", "deploy hardpoints", "heatsink", "request docking"):
            self.assertIsNotNone(matcher.match(text), text)


class GameTests(Base):
    def test_where_are_we(self):
        reply = self.ask("where are we")
        self.assertIn("Sol", reply)

    def test_where_when_docked(self):
        self.state.docked, self.state.station = True, "Abraham Lincoln"
        self.assertIn("Abraham Lincoln", self.ask("where am I"))

    def test_unknown_position(self):
        self.state.system = None
        reply = self.ask("where are we")
        self.assertNotIn("None", reply)

    def test_ship(self):
        self.assertIn("Python", self.ask("what ship am I flying"))

    def test_status_healthy_and_hurt(self):
        self.assertIn("100", self.ask("status report"))
        self.state.hull_health = 0.3
        self.assertIn("30", self.ask("how's the ship"))

    def test_status_mentions_a_bounty(self):
        self.state.wanted = True
        self.ask("status report")
        self.assertIn("wanted", self.speech.said[-1]["text"].lower())

    def test_wanted(self):
        self.state.wanted = True
        yes = self.ask("am I wanted")
        self.state.wanted = False
        no = self.ask("am I wanted")
        self.assertNotEqual(yes, no)

    def test_time_and_date_are_real(self):
        self.assertIn("21:50", self.ask("what time is it"))
        self.assertIn("Monday the 19th of October", self.ask("what's the date"))

    def test_my_name(self):
        self.assertIn("Dave", self.ask("what's my name"))

    def test_suggestions_follow_the_situation(self):
        self.state.hull_health = 0.2
        self.assertTrue(self.ask("what should we do"))
        self.assertEqual(self.brain.topic[0], "Brain_Suggest")

    def test_coin_dice_number(self):
        self.assertRegex(self.ask("flip a coin"), "Heads|Tails")
        self.assertTrue(re.search(r"\b[1-6]\b", self.ask("roll a dice")))
        reply = self.ask("pick a number between 40 and 50")
        self.assertTrue(40 <= int(re.search(r"\d+", reply).group()) <= 50)

    def test_dice_sides(self):
        reply = self.ask("roll a d20")
        self.assertTrue(re.search(r"\d+", reply))

    def test_fact(self):
        self.assertIn("neutron star", self.ask("tell me a fun fact"))

    def test_opinion_uses_what_you_said(self):
        self.assertIn("pulse lasers", self.ask("what do you think about pulse lasers"))

    def test_opinion_ignores_long_rambles(self):
        self.assertIsNone(self.ask("what do you think about the fact that all of this is really quite complicated"))


class FollowUpTests(Base):
    def test_why_more_you_really(self):
        self.ask("what's your favourite colour")
        for text in ("why", "tell me more", "what about you", "really"):
            self.speech.said.clear()
            self.assertIsNotNone(self.ask(text), text)
            self.assertEqual(len(self.speech.said), 1)

    def test_topic_specific_follow_up_is_used(self):
        self.ask("do you dream")
        reply = self.ask("tell me more")
        self.assertIn(reply, [l.text for l in self.dialogue.lines["Brain_Dream_More"]])

    def test_without_a_topic_follow_ups_do_nothing(self):
        for text in ("why", "tell me more", "really"):
            self.assertIsNone(self.ask(text), text)

    def test_topic_expires(self):
        self.ask("do you dream")
        self.clock.now += 400
        self.assertIsNone(self.ask("why"))

    def test_follow_up_keeps_the_topic(self):
        self.ask("do you dream")
        self.ask("tell me more")
        self.assertEqual(self.topic(), "Brain_Dream")


class RiddleTests(Base):
    def test_right_answer(self):
        self.ask("tell me a riddle")
        answers = self.brain.riddle[0]
        self.assertTrue(self.brain.waiting())
        reply = self.ask("is it %s" % answers[0], deliberate=False)       # no wake word needed while she waits
        self.assertIsNotNone(reply)
        self.assertIsNone(self.brain.riddle)

    def test_give_up_reveals_the_answer(self):
        self.ask("tell me a riddle")
        answer = self.brain.riddle[1]
        reply = self.ask("I give up")
        self.assertIn(answer, reply)

    def test_give_up_with_no_riddle(self):
        self.assertIsNone(self.ask("I give up"))

    def test_riddle_expires(self):
        self.ask("tell me a riddle")
        self.clock.now += 500
        self.assertFalse(self.brain.waiting())

    def test_no_repeat_until_all_used(self):
        seen = set()
        for _ in range(12):
            self.ask("tell me a riddle")
            seen.add(self.brain.riddle[1])
        self.assertEqual(len(seen), 12)


class MoodTests(Base):
    def test_sarcastic_lines_can_appear(self):
        self.settings.set("personality.mood_live", "Sarcastic")
        self.settings.set("personality.mood_mode", "manual")
        self.settings.set("personality.mood", "Sarcastic")
        pool = [l.text for l in self.dialogue.pool("Brain_Insulted", "Sarcastic", False, False)]
        self.assertGreater(len(pool), len(self.dialogue.pool("Brain_Insulted", "", False, False)))

    def test_mature_lines_need_the_switch(self):
        mature = [l for l in self.dialogue.lines.get("Brain_Roast_Sarcastic", []) if l.mature]
        self.assertTrue(mature)
        self.assertNotIn(mature[0], self.dialogue.pool("Brain_Roast", "Sarcastic", False, False))
        self.assertIn(mature[0], self.dialogue.pool("Brain_Roast", "Sarcastic", True, False))


class RunnerTests(unittest.TestCase):
    """The brain is only asked after the command matcher found nothing."""

    def setUp(self):
        from tests.test_commands import RunnerTests as R
        base = R("runner")
        base.setUp()
        self.base = base
        self.asked = []
        outer = self

        class Stub:
            def try_handle(self, text, deliberate=True):
                outer.asked.append((text, deliberate))
                return "an answer" if "colour" in text else None

        self.stub = Stub()

    def runner(self):
        from control.runner import CommandRunner
        from tests.test_commands import make_settings
        r = CommandRunner(self.base.bus, self.base.speech, self.base.dialogue, make_settings(), book=self.base.book,
                          sender=self.base.sender, state_provider=lambda: self.base.state, clock=lambda: self.base.now[0],
                          sleep=lambda s: None, brain=self.stub)
        r.attach()
        return r

    def test_commands_never_reach_the_brain(self):
        runner = self.runner()
        runner.run_text("lower the landing gear")
        self.assertEqual(self.asked, [])
        self.assertTrue(self.base.sender.pressed)

    def test_unknown_text_goes_to_the_brain_and_is_answered(self):
        runner = self.runner()
        outcomes = runner.run_text("what's your favourite colour")
        self.assertEqual(self.asked, [("what's your favourite colour", True)])
        self.assertEqual(outcomes[0].detail, "an answer")
        self.assertFalse(self.base.sender.pressed)

    def test_unknown_stays_unknown_if_the_brain_has_nothing(self):
        runner = self.runner()
        outcomes = runner.run_text("blah blah blah")
        self.assertEqual(outcomes[0].kind if hasattr(outcomes[0], "kind") else "unknown", "unknown")

    def test_background_chatter_is_not_deliberate(self):
        runner = self.runner()
        runner.run_text("what's your favourite colour", speak_unknown=False)
        self.assertEqual(self.asked[0][1], False)


if __name__ == "__main__":
    unittest.main()
