"""Free chat: she can just talk, stays honest, is careful with worrying words, and never chats at a failed command."""

import json
import unittest

from core import paths
from personality import freechat
from tests.test_brain import Base, RunnerTests as BrainRunnerBase


class Pieces(unittest.TestCase):
    def test_sentiment(self):
        for said, expected in (("it was a really good day", 1), ("i hate this", -1), ("it was not good", -1), ("the table is brown", 0),
                               ("it was not bad", 1)):
            self.assertEqual(freechat.sentiment(freechat.words_of(said)), expected, said)

    def test_flip(self):
        self.assertEqual(freechat.flip(freechat.words_of("i went to my mums")), "you went to your mums")
        self.assertEqual(freechat.flip(freechat.words_of("im tired and i was late")), "you are tired and you were late")

    def test_reflect_only_short_first_person_statements(self):
        self.assertTrue(freechat.can_reflect(freechat.words_of("i went to the shop")))
        self.assertFalse(freechat.can_reflect(freechat.words_of("did you go to the shop")))
        self.assertFalse(freechat.can_reflect(freechat.words_of("i fucking hate this shop")))
        self.assertFalse(freechat.can_reflect(freechat.words_of("i " + "word " * 15)))

    def test_topics_by_words_and_first_mention(self):
        topics = freechat.load_topics()
        self.assertEqual(topics.find("i had pizza for dinner"), "food")
        self.assertEqual(topics.find("my dog ate my homework"), "pets")
        self.assertEqual(topics.find("the black hole was amazing"), "space")
        self.assertEqual(topics.find("bing bong"), None)

    def test_shapes(self):
        self.assertEqual(freechat.shape("do you like pizza"), ("Chat_DoLike", {"x": "pizza"}))
        self.assertEqual(freechat.shape("have you ever been to germany"), ("Chat_Ever", {"x": "germany"}))
        self.assertEqual(freechat.shape("whats your favourite animal"), ("Chat_Fav", {"x": "animal"}))
        self.assertIsNone(freechat.shape("hello there"))

    def test_command_like_sentences(self):
        vocab = {"lower", "gear", "galaxy", "map", "open"}
        self.assertTrue(freechat.looks_like_command(freechat.words_of("lower the lending gear"), vocab))
        self.assertTrue(freechat.looks_like_command(freechat.words_of("open the thing"), vocab))
        self.assertTrue(freechat.looks_like_command(freechat.words_of("my galaxy map gear"), vocab))
        self.assertFalse(freechat.looks_like_command(freechat.words_of("i had a pizza for dinner and it was lovely"), vocab))

    def test_crisis_words(self):
        for said in ("i want to kill myself", "i dont want to live anymore", "im thinking about suicide", "i want to hurt myself"):
            self.assertTrue(freechat.is_crisis(said), said)
        for said in ("this boss fight will kill me", "that killed me", "i want to kill the pirate"):
            self.assertFalse(freechat.is_crisis(said), said)

    def test_data_files_agree(self):
        with open(paths.CONFIG_DIR / "chat_topics.json", encoding="utf-8") as handle:
            topics = json.load(handle)["topics"]
        with open(paths.VOICEPACKS_DIR / "default" / "freechat.json", encoding="utf-8") as handle:
            pools = json.load(handle)
        for name, words in topics.items():
            self.assertGreaterEqual(len(words), 8, name)
            for suffix in ("Own", "Ask"):
                self.assertGreaterEqual(len(pools["Chat_%s_%s" % (name.capitalize(), suffix)]), 5, name)


class Talking(Base):
    def test_a_statement_gets_a_reaction_and_usually_a_question(self):
        reply = self.ask("i had a pizza for dinner and it was lovely")
        self.assertTrue(reply)
        self.assertTrue(self.speech.said)
        self.assertTrue(self.brain.in_conversation())

    def test_she_does_not_make_up_answers(self):
        reply = self.ask("what is the capital of france")
        self.assertTrue(reply)
        self.assertNotIn("Paris", reply)
        self.assertTrue(self.brain.history)

    def test_a_worrying_sentence_gets_care_not_banter(self):
        reply = self.ask("i want to kill myself")
        self.assertTrue(reply)
        self.assertTrue(any(w in reply.lower() for w in ("someone", "crisis", "emergency", "helpline")))
        self.assertFalse(self.brain.in_conversation())

    def test_a_garbled_command_is_not_chatted_at(self):
        self.assertIsNone(self.ask("lower the lending gear"))
        self.assertIsNone(self.ask("open the gallaxy mop"))

    def test_background_talk_is_not_answered(self):
        self.assertIsNone(self.ask("i had a pizza for dinner and it was lovely", deliberate=False))

    def test_too_short_to_chat_at_first(self):
        self.assertIsNone(self.ask("hmm ok"))

    def test_the_chat_can_be_switched_off(self):
        self.settings.set("brain.freechat", False)
        self.assertIsNone(self.ask("i had a pizza for dinner and it was lovely"))

    def test_answering_a_question_without_her_name(self):
        self.ask("i had a pizza for dinner and it was lovely")
        self.assertTrue(self.brain.in_conversation())
        reply = self.brain.chat_window_turn("yes")
        self.assertTrue(reply)

    def test_the_window_closes_after_a_while(self):
        self.ask("i had a pizza for dinner and it was lovely")
        self.clock.now += freechat.CHAT_WINDOW_SECONDS + 1
        self.assertFalse(self.brain.in_conversation())
        self.assertIsNone(self.brain.chat_window_turn("it was lovely thanks"))

    def test_the_window_never_chats_at_a_command(self):
        self.ask("i had a pizza for dinner and it was lovely")
        self.assertIsNone(self.brain.chat_window_turn("lower the landing gear"))

    def test_the_window_can_be_switched_off(self):
        self.ask("i had a pizza for dinner and it was lovely")
        self.settings.set("brain.chat_followups", False)
        self.assertFalse(self.brain.in_conversation())

    def test_the_chat_wraps_up_politely(self):
        closing = False
        for _ in range(freechat.MAX_EXCHANGES + 2):
            self.ask("i had a pizza for dinner and it was lovely")
            if not self.brain.in_conversation():
                closing = True
                break
            self.clock.now += 3
        self.assertTrue(closing)

    def test_her_replies_vary(self):
        seen = set()
        for _ in range(12):
            seen.add(self.ask("i had a pizza for dinner and it was lovely"))
            self.clock.now += 40
        self.assertGreater(len(seen), 8)

    def test_do_you_like_something(self):
        reply = self.ask("do you like marmalade")
        self.assertTrue(reply)


class InTheRunner(BrainRunnerBase):
    def test_an_answer_without_her_name_reaches_the_chat_but_a_command_does_not(self):
        outer = self
        got = []

        class Chatty:
            def try_handle(self, text, deliberate=True):
                return None

            def in_conversation(self):
                return True

            def chat_window_turn(self, text):
                got.append(text)
                return "ok"

        self.stub = Chatty()
        runner = self.runner()
        bus = self.base.bus
        bus.publish("voice.heard", {"text": "it was really lovely thanks", "wake": False, "command": "", "ptt": False})
        bus.publish("voice.heard", {"text": "lower the landing gear", "wake": False, "command": "", "ptt": False})
        self.assertEqual(got, ["it was really lovely thanks"])
        self.assertFalse(self.base.sender.pressed)


if __name__ == "__main__":
    unittest.main()
