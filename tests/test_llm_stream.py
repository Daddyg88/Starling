"""Sentence by sentence: she starts after the first sentence and the model carries on writing while she speaks."""

import threading
import time
import unittest

from personality.llm import LocalLLM, build_messages, sentence_end
from tests.test_llm import FakeModel
from tests.test_brain import Base


class Settings(dict):
    def get(self, key, default=None):
        return dict.get(self, key, default)


class Streamer:
    """A model that writes its answer in small pieces, like the real engine."""

    def __init__(self, pieces, gap=0.0):
        self.pieces, self.gap, self.closed = pieces, gap, False

    def stream_chat_completion(self, **kwargs):
        try:
            for piece in self.pieces:
                if self.gap:
                    time.sleep(self.gap)
                yield piece
        finally:
            self.closed = True


def llm_with(model):
    return LocalLLM(Settings({"llm.enabled": True, "llm.max_seconds": 5}), loader=lambda path, threads: model)


TEXT = ["Exploring is my favourite thing, ", "Commander. ", "Nothing beats a silent neutron star. ", "Want to go and see one? ", "Maybe later "]


class SentenceEnd(unittest.TestCase):
    def test_needs_the_space_after_the_full_stop(self):
        self.assertIsNone(sentence_end("It is 7.5"))
        self.assertIsNone(sentence_end("Still writing this one."))
        self.assertEqual(sentence_end("Done. Next"), 6)

    def test_length_text(self):
        self.assertIn("ONE short sentence", build_messages("hello there", sentences=1)[0]["content"])
        self.assertIn("one to three short sentences", build_messages("hello there", sentences=3)[0]["content"])


class Stream(unittest.TestCase):
    def test_each_sentence_is_passed_on_as_it_is_finished(self):
        model, got = Streamer(TEXT), []
        said = llm_with(model).reply_stream([], got.append, max_sentences=3)
        self.assertEqual(got, ["Exploring is my favourite thing, Commander.", "Nothing beats a silent neutron star.", "Want to go and see one?"])
        self.assertEqual(said, " ".join(got))

    def test_stops_at_the_limit_and_tells_the_model_to_stop(self):
        model, got = Streamer(TEXT, gap=0.01), []
        llm_with(model).reply_stream([], got.append, max_sentences=1)
        self.assertEqual(len(got), 1)
        time.sleep(0.3)
        self.assertTrue(model.closed)

    def test_first_sentence_is_said_before_the_model_has_finished(self):
        order, release = [], threading.Event()

        class Slow(Streamer):
            def stream_chat_completion(self, **kwargs):
                yield "I am ready to go, Commander. "
                release.wait(3)
                order.append("model finished")
                yield "And so is the ship. "
        llm_with(Slow([])).reply_stream([], lambda text: (order.append(text), release.set()), max_sentences=2)
        self.assertEqual(order[0], "I am ready to go, Commander.")
        self.assertIn("model finished", order)

    def test_a_bad_sentence_stops_everything_after_it(self):
        got = []
        said = llm_with(Streamer(["Fine, that sounds great Commander. ", "Visit www.example.com for more. ", "Another good one here. "])).reply_stream(
            [], got.append, max_sentences=3)
        self.assertEqual(got, ["Fine, that sounds great Commander."])
        self.assertEqual(said, "Fine, that sounds great Commander.")

    def test_a_bad_first_sentence_gives_none(self):
        self.assertIsNone(llm_with(Streamer(["As an AI language model I cannot do that. "])).reply_stream([], lambda t: None))

    def test_tiny_sentences_are_joined_to_the_next(self):
        got = []
        llm_with(Streamer(["Ha. ", "That is a really good one. "])).reply_stream([], got.append, max_sentences=2)
        self.assertEqual(got, ["Ha. That is a really good one."])

    def test_a_model_that_cannot_stream_is_one_sentence(self):
        got = []
        llm_with(FakeModel()).reply_stream([], got.append)
        self.assertEqual(len(got), 1)

    def test_thinking_sound_while_nothing_has_arrived(self):
        waits, got = [], []
        llm_with(Streamer(["Well that took a while to write, Commander. "], gap=0.7)).reply_stream(
            [], got.append, on_wait=lambda: waits.append(1), wait_after=0.3)
        self.assertEqual(waits, [1])
        self.assertEqual(len(got), 1)

    def test_no_thinking_sound_when_the_first_sentence_is_quick(self):
        waits = []
        llm_with(Streamer(["That is quick enough, Commander. "])).reply_stream([], lambda t: None, on_wait=lambda: waits.append(1), wait_after=1.0)
        self.assertEqual(waits, [])

    def test_gives_up_quietly_when_too_slow(self):
        model = Streamer(["Too late now, Commander. "], gap=1.5)
        llm = llm_with(model)
        llm.settings["llm.max_seconds"] = 0.4
        self.assertIsNone(llm.reply_stream([], lambda t: None))


class BrainSpeaksEachSentence(Base):
    CHAT = "i spent the whole afternoon repainting the garden fence"

    def said(self):
        return [item["text"] for item in self.speech.said]

    def run_it(self, pieces, sentences=3, gap=0.0):
        from tests.test_llm import make
        self.settings.set("llm.max_sentences", sentences)
        make(self, Streamer(pieces, gap=gap))
        self.brain._vocab()
        return self.ask(self.CHAT)

    def test_each_sentence_is_spoken_once_in_order(self):
        reply = self.run_it(TEXT)
        self.assertEqual(self.said(), ["Exploring is my favourite thing, Commander.", "Nothing beats a silent neutron star.", "Want to go and see one?"])
        self.assertEqual(reply, " ".join(self.said()))

    def test_one_sentence_setting_uses_the_whole_answer_path(self):
        from tests.test_llm import make, FakeModel
        self.settings.set("llm.max_sentences", 1)
        model = FakeModel()
        make(self, model)
        self.brain._vocab()
        self.ask(self.CHAT)
        self.assertEqual(len(self.said()), 1)
        self.assertIn("ONE short sentence", model.calls[0]["messages"][0]["content"])

    def test_unusable_stream_falls_back_to_her_normal_lines(self):
        reply = self.run_it(["As an AI language model I cannot do that. "])
        self.assertTrue(reply)
        self.assertEqual(len(self.said()), 1)
        self.assertNotIn("language model", self.said()[0])

    def test_hmm_then_the_sentences_when_the_model_is_slow(self):
        self.settings.set("brain.thinking_after", 0.1)
        self.run_it(TEXT, gap=0.15)
        said = self.said()
        self.assertEqual(len(said), 4)
        self.assertIn(said[0], [line.text for line in self.dialogue.pool("Brain_Thinking", "Friendly", True, False)])


if __name__ == "__main__":
    unittest.main()
