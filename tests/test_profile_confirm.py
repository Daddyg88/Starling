"""The player profile ("I love pizza") and "did you mean...?"."""

import json
import tempfile
import unittest
from pathlib import Path

from control.confirm import Confirmer, WINDOW_SECONDS
from control.learning import VoiceLearning
from control.matcher import Matcher
from memory.profile import PlayerProfile, acceptable
from tests.test_brain import Base
from tests.test_commands import RunnerTests as CommandBase


class Profile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "profile.json"
        self.profile = PlayerProfile(self.path)

    def test_learning_the_four_kinds(self):
        self.assertEqual(self.profile.learn("i love pizza"), ("like", {"x": "pizza"}, True))
        self.assertEqual(self.profile.learn("i really hate mining")[0], "dislike")
        self.assertEqual(self.profile.learn("my dog is called rex"), ("pet", {"kind": "dog", "name": "Rex"}, True))
        self.assertEqual(self.profile.learn("my favourite colour is blue")[0], "fav")

    def test_the_same_thing_twice_is_not_new(self):
        self.profile.learn("i love pizza")
        self.assertFalse(self.profile.learn("i love pizza")[2])
        self.assertEqual(self.profile.likes, ["pizza"])

    def test_changing_your_mind(self):
        self.profile.learn("i love pizza")
        self.profile.learn("i hate pizza")
        self.assertEqual((self.profile.likes, self.profile.dislikes), ([], ["pizza"]))

    def test_things_she_must_not_keep(self):
        for said in ("i love my mum", "i hate my boss", "i love you", "i hate religion", "i love drugs", "i like weed",
                     "i hate my job and my boss and everything", "i love flying with you and my dog", "my cat is very cute",
                     "i love 12345", "i love it", "i hate when people talk", "my favourite party is blue"):
            self.assertIsNone(self.profile.learn(said), said)
        self.assertTrue(self.profile.is_empty())
        self.assertFalse(acceptable("my sister"))

    def test_it_can_be_switched_off(self):
        off = PlayerProfile(self.path, enabled=lambda: False)
        self.assertIsNone(off.learn("i love pizza"))
        self.assertIsNone(off.mentions("pizza tonight"))

    def test_saved_and_reloaded(self):
        self.profile.learn("i love pizza")
        self.profile.learn("my cat is called mittens")
        again = PlayerProfile(self.path)
        self.assertEqual(again.likes, ["pizza"])
        self.assertEqual(again.pets[0]["name"], "mittens")

    def test_a_broken_file_is_survived(self):
        self.path.write_text("not json at all", encoding="utf-8")
        self.assertTrue(PlayerProfile(self.path).is_empty())

    def test_mentions(self):
        self.profile.learn("i love pizza")
        self.profile.learn("my dog is called rex")
        self.assertEqual(self.profile.mentions("we had pizza for tea")[0], "like")
        self.assertEqual(self.profile.mentions("rex is barking again")[0], "pet")
        self.assertIsNone(self.profile.mentions("the weather is nice"))

    def test_forgetting(self):
        self.profile.learn("i love pizza")
        self.profile.learn("i love chips")
        self.assertEqual(self.profile.forget("forget that i love pizza"), "one")
        self.assertEqual(self.profile.likes, ["chips"])
        self.assertEqual(self.profile.forget("forget everything about me"), "all")
        self.assertTrue(self.profile.is_empty())
        self.assertIsNone(self.profile.forget("forget it"))

    def test_the_file_is_limited_in_size(self):
        for number in range(60):
            self.profile.learn("i love thing%s" % "abcdefghijklmnopqrstuvwxyz"[number % 26] * 1)
        self.assertLessEqual(len(self.profile.likes), 30)


class InTheBrain(Base):
    def setUp(self):
        super().setUp()
        self.tmp2 = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp2.cleanup)
        self.profile = PlayerProfile(Path(self.tmp2.name) / "p.json")
        self.brain.profile = self.profile

    def test_she_says_what_she_learned(self):
        reply = self.ask("i love pizza")
        self.assertIn("pizza", reply.lower())
        self.assertEqual(self.profile.likes, ["pizza"])

    def test_she_says_when_she_already_knew(self):
        self.ask("i love pizza")
        reply = self.ask("i love pizza")
        self.assertIn("pizza", reply.lower())
        self.assertEqual(self.profile.likes, ["pizza"])

    def test_nothing_is_learned_from_background_talk(self):
        self.ask("i love pizza", deliberate=False)
        self.assertTrue(self.profile.is_empty())

    def test_what_do_you_know_about_me(self):
        self.assertIn("pizza", (self.ask("i love pizza"), self.ask("what do you know about me"))[1].lower())
        self.ask("my dog is called rex")
        self.assertIn("rex", self.ask("what do you know about me").lower())

    def test_nothing_known_yet(self):
        self.assertTrue(self.ask("what do you know about me"))

    def test_what_is_my_dogs_name(self):
        self.ask("my dog is called rex")
        self.assertIn("Rex", self.ask("whats my dog called"))

    def test_my_favourite(self):
        self.ask("my favourite colour is blue")
        self.assertIn("blue", self.ask("whats my favourite colour"))

    def test_forget_by_voice(self):
        self.ask("i love pizza")
        self.ask("forget that i love pizza")
        self.assertEqual(self.profile.likes, [])
        self.ask("my dog is called rex")
        self.ask("forget what you know about me")
        self.assertTrue(self.profile.is_empty())

    def test_she_brings_it_up_in_chat(self):
        self.ask("i love pizza")
        self.clock.now += 100
        mentioned = 0
        for _ in range(20):
            reply = self.ask("we had pizza for dinner tonight and it was lovely")
            self.clock.now += 40
            if reply and any(m in reply.lower() for m in ("told me", "one of your favourites", "remember you like")):
                mentioned += 1
        self.assertGreater(mentioned, 3)

    def test_the_switch(self):
        self.settings.set("brain.profile", False)
        self.ask("i love pizza")
        self.assertTrue(self.profile.is_empty())

    def test_profile_lines_only_use_known_fields(self):
        import re
        known = {"x", "X", "name", "kind", "cat", "likes", "dislikes", "pets", "favs", "phrase"}
        for key, lines in self.dialogue.lines.items():
            if key.startswith(("Profile_", "Chat_Known", "CommandConfirm")):
                for line in lines:
                    for field in re.findall(r"\{(\w+)\}", line.text):
                        self.assertIn(field, known, "%s: %s" % (key, line.text))

    def test_the_voice_pack_has_every_line(self):
        for key in ("Profile_Learned_Like", "Profile_Learned_Dislike", "Profile_Learned_Pet", "Profile_Learned_Fav", "Profile_Known_Like",
                    "Profile_Empty", "Profile_ForgotAll", "Chat_Known_Pet", "CommandConfirm", "CommandConfirmNo"):
            self.assertTrue(self.dialogue.pool(key, "", True, False), key)


class Suggest(unittest.TestCase):
    def setUp(self):
        self.m = Matcher()

    def test_a_near_miss_is_suggested(self):
        found = self.m.suggest("open the galax map please")
        self.assertEqual((found.command.id, found.how), ("galaxy_map", "suggest"))

    def test_a_big_action_is_suggested_not_run(self):
        self.assertIsNone(self.m.match("hyperspace jum"))
        self.assertEqual(self.m.suggest("hyperspace jum").command.id, "hyperspace")

    def test_the_opposite_is_never_suggested(self):
        found = self.m.suggest("lower the landin gear")
        self.assertTrue(found is None or found.intent == "on")

    def test_chat_is_not_suggested_as_a_command(self):
        for said in ("what is the weather", "i had pizza for dinner", "tell me a story about a dragon"):
            self.assertIsNone(self.m.suggest(said), said)


class Confirming(unittest.TestCase):
    def test_yes_no_and_neither(self):
        now = [0.0]
        c = Confirmer(lambda: now[0])
        self.assertIsNone(c.answer("yes"))                    # nothing was asked
        c.ask("m", "heard")
        self.assertEqual(c.answer("Yes please!"), "yes")
        c.ask("m", "heard")
        self.assertEqual(c.answer("nope"), "no")
        c.ask("m", "heard")
        self.assertIsNone(c.answer("open the galaxy map"))
        self.assertFalse(c.active())

    def test_the_question_expires(self):
        now = [0.0]
        c = Confirmer(lambda: now[0])
        c.ask("m", "heard")
        now[0] += WINDOW_SECONDS + 1
        self.assertFalse(c.active())
        self.assertIsNone(c.answer("yes"))

    def test_hey_starling_yes(self):
        c = Confirmer(lambda: 0.0)
        c.ask("m", "heard")
        self.assertEqual(c.answer("Starling yes"), "yes")


class InTheRunner(unittest.TestCase):
    def setUp(self):
        base = CommandBase("runner")
        base.setUp()
        self.base = base
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.learn = VoiceLearning(Path(self.tmpdir.name) / "l.json")
        from control.runner import CommandRunner
        from tests.test_commands import make_settings
        self.runner = CommandRunner(base.bus, base.speech, base.dialogue, make_settings(), book=base.book, sender=base.sender,
                                    state_provider=lambda: base.state, clock=lambda: base.now[0], sleep=lambda s: None,
                                    matcher=Matcher(learning=self.learn))
        self.runner.attach()
        self.sender = base.sender

    def heard(self, text, wake=False):
        self.base.bus.publish("voice.heard", {"text": text, "wake": wake, "command": text if wake else "", "ptt": False})

    def test_she_asks_then_does_it_on_yes_and_learns(self):
        outcomes = self.runner.run_text("opn galaxi map")
        self.assertEqual(outcomes[0].status, "asked")
        self.assertFalse(self.sender.pressed)
        self.assertTrue(self.base.speech.said)                     # she asked out loud
        self.heard("yes")
        self.assertTrue(self.sender.pressed)
        self.assertEqual(self.learn.learned("opn galaxi map"), "galaxy map")

    def test_no_drops_it_and_she_does_not_ask_again(self):
        self.runner.run_text("opn galaxi map")
        self.heard("no")
        self.assertFalse(self.sender.pressed)
        self.assertEqual(self.runner.run_text("opn galaxi map")[0].status, "unknown")

    def test_a_big_action_waits_for_a_yes_and_is_not_remembered(self):
        outcomes = self.runner.run_text("hyperspace jum")
        self.assertEqual(outcomes[0].status, "asked")
        self.assertFalse(self.sender.pressed)
        self.heard("yes")
        self.assertEqual(self.runner.last_outcomes[0].command.id, "hyperspace")        # it was tried (the test keybinds have no jump key)
        self.assertIsNone(self.learn.learned("hyperspace jum"))

    def test_background_talk_is_never_questioned(self):
        outcomes = self.runner.run_text("opn galaxi map", speak_unknown=False)
        self.assertNotEqual(outcomes[0].status, "asked")

    def test_the_switch(self):
        self.runner.settings.set("commands.ask_guess", False)
        self.assertEqual(self.runner.run_text("opn galaxi map")[0].status, "unknown")

    def test_something_else_cancels_the_question(self):
        self.runner.run_text("opn galaxi map")
        self.heard("lower the landing gear", wake=True)
        self.assertFalse(self.runner.confirmer.active())

    def test_a_late_yes_does_nothing(self):
        self.runner.run_text("opn galaxi map")
        self.base.now[0] += WINDOW_SECONDS + 1
        self.heard("yes")
        self.assertFalse(self.sender.pressed)


if __name__ == "__main__":
    unittest.main()
