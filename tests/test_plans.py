"""Tests: 'What are we doing today?' - understanding answers, the one activity she dislikes, mood points, the engineer fix."""

import random
import unittest

from personality.plans import TOPICS, topic_from
from tests.test_ask_and_paint import Rig


class UnderstandingTests(unittest.TestCase):
    def test_natural_answers(self):
        cases = {
            "I think we shall go out exploring": "exploring", "maybe we will go mining today": "mining",
            "some bounty hunting": "combat", "lets do some trading": "trading", "scan some bio planets": "exobiology",
            "lets hunt thargoids": "antixeno", "anti xeno": "antixeno", "anti zeno today": "antixeno",
            "nothing really": "none", "surprise me": "none",
        }
        for said, topic in cases.items():
            self.assertEqual(topic_from(said), topic, said)

    def test_other_sentences_are_not_answers(self):
        self.assertIsNone(topic_from("deploy hardpoints"))
        self.assertIsNone(topic_from(""))
        self.assertIsNone(topic_from("a very long sentence " * 6 + "mining"))


class PlanFlowTests(unittest.TestCase):
    def asked(self, seed=1):
        r = Rig()
        r.ask.rng = random.Random(seed)
        self.assertTrue(r.ask.ask_plan())
        self.assertIn("doing today", r.speech.said[-1]["text"].lower())
        self.assertEqual(r.speech.said[-1]["event_name"], "ask.question")
        r.finish_question()
        return r

    def test_exactly_one_choice_costs_a_point_and_the_rest_earn_one(self):
        for seed in range(4):
            bad = good = 0
            for topic in TOPICS:
                r = self.asked(seed)
                before = r.mood.score
                r.say("let's go " + {"exploring": "exploring", "mining": "mining", "combat": "fighting", "trading": "trading",
                                     "exobiology": "bio sampling", "antixeno": "hunting thargoids"}[topic])
                if r.mood.score < before:
                    bad += 1
                elif r.mood.score > before:
                    good += 1
            self.assertEqual((bad, good), (1, 5), seed)

    def test_she_grumbles_but_goes_when_it_is_the_disliked_one(self):
        r = self.asked()
        disliked = r.ask.pending["data"]["disliked"]
        word = {"exploring": "exploring", "mining": "mining", "combat": "fighting", "trading": "trading",
                "exobiology": "bio sampling", "antixeno": "hunting thargoids"}[disliked]
        r.say("maybe we will go " + word)
        said = r.speech.said[-1]["text"].lower()
        self.assertIn("anyway", said)

    def test_asked_once_per_login_and_new_login_picks_again(self):
        r = Rig()
        self.assertTrue(r.ask.ask_plan())
        r.ask._drop_pending_quietly()
        self.assertFalse(r.ask.ask_plan())
        r.bus.publish("LoadGame", {}, "normal")
        r.ask._drop_pending_quietly()
        self.assertTrue(r.ask.ask_plan())

    def test_it_follows_the_login_greeting_and_the_setting_turns_it_off(self):
        r = Rig()
        r.bus.publish("speech.finished", {"event": "login.greeting", "text": "hello"}, "low")
        r.fire_timers()
        self.assertTrue(any("doing today" in s["text"].lower() for s in r.speech.said))
        r2 = Rig(plans__ask=False)
        self.assertFalse(r2.ask.ask_plan())

    def test_no_question_when_she_cannot_hear_and_silence_costs_nothing(self):
        r = Rig()
        r.listening = False
        self.assertFalse(r.ask.ask_plan())
        r = self.asked()
        before = r.mood.score
        r.expire_answer_window()
        self.assertEqual(r.mood.score, before)

    def test_started_during_a_game_she_asks_after_a_moment(self):
        r = Rig()
        r.ask.schedule_midgame(lambda: True)
        r.fire_timers()
        self.assertTrue(any("doing today" in s["text"].lower() for s in r.speech.said))

    def test_every_activity_has_several_lines_each_way(self):
        from personality.dialogue import DialogueManager
        from core import paths
        d = DialogueManager(paths.VOICEPACKS_DIR / "default").load()
        self.assertGreaterEqual(len(d.lines.get("Plan_Ask", [])), 6)
        for topic in TOPICS:
            self.assertGreaterEqual(len(d.lines.get("Plan_Like_" + topic, [])), 5, topic)
            self.assertGreaterEqual(len(d.lines.get("Plan_Dislike_" + topic, [])), 4, topic)
            self.assertTrue(all("anyway" in l.text.lower()
                                for l in d.lines["Plan_Dislike_" + topic]), topic)


class EngineerStartupTests(unittest.TestCase):
    def test_the_login_list_is_silent_but_real_progress_is_announced(self):
        from events.engineer_progress import EngineerProgress
        event = EngineerProgress()
        event.update_state({"event": "EngineerProgress", "Engineers": [{"Engineer": "Hera Tani", "Progress": "Known"}]}, None)
        self.assertFalse(event.announce)
        event.update_state({"event": "EngineerProgress", "Engineer": "Hera Tani", "Progress": "Invited"}, None)
        self.assertTrue(event.announce)


if __name__ == "__main__":
    unittest.main()
