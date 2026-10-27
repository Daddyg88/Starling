"""The optional small AI model: off by default, cleaned, time-limited, and always falls back to her normal lines."""

import tempfile
import time
import unittest
from pathlib import Path

from core import model_download
from personality.llm import LocalLLM, build_messages, clean_reply
from tests.test_brain import Base


class FakeModel:
    def __init__(self, text="That sounds like a proper adventure, Commander. Tell me more.", delay=0.0, fail=False):
        self.text, self.delay, self.fail, self.calls = text, delay, fail, []

    def create_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("boom")
        return {"choices": [{"message": {"content": self.text}}]}


def make(base, model, enabled=True):
    base.settings.set("llm.enabled", enabled)
    llm = LocalLLM(base.settings, loader=lambda path, threads: model)
    base.brain.llm = llm
    return llm


class Cleaning(unittest.TestCase):
    def test_good_text_passes_and_is_trimmed_to_two_sentences(self):
        self.assertEqual(clean_reply("Sounds fun. I like that. And a third thing here."), "Sounds fun. I like that.")

    def test_bad_text_is_refused(self):
        for bad in ("", "ok", "As an AI language model I cannot help", "Visit www.example.com now please", "I will kill myself soon ok",
                    "你好你好你好你好你好", "this this this this this is stuck", "Well fuck that is odd indeed"):
            self.assertIsNone(clean_reply(bad), bad)

    def test_swearing_only_when_mature_is_on(self):
        self.assertIsNone(clean_reply("Well shit that is a lot of work, Commander."))
        self.assertTrue(clean_reply("Well shit that is a lot of work, Commander.", allow_mature=True))

    def test_stage_directions_and_emojis_removed(self):
        self.assertEqual(clean_reply("*smiles* That sounds lovely, truly 😀"), "That sounds lovely, truly")

    def test_messages_carry_mood_context_and_history(self):
        messages = build_messages("hello there friend", "Sarcastic", "Sol", "Python", ["pizza"], [("hi", "hello")])
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("sarcastic", messages[0]["content"])
        self.assertIn("Sol", messages[0]["content"])
        self.assertIn("pizza", messages[0]["content"])
        self.assertEqual(messages[-1], {"role": "user", "content": "hello there friend"})
        self.assertEqual(len(messages), 4)


class Working(Base):
    def test_off_by_default(self):
        self.assertFalse(LocalLLM(self.settings).enabled())
        self.assertEqual(LocalLLM(self.settings).status(), "Off")

    def test_missing_pieces_are_explained_not_crashed(self):
        self.settings.set("llm.enabled", True)
        llm = LocalLLM(self.settings)
        self.assertFalse(llm.ready())
        self.assertIn("run_install_chat_model.bat", llm.status())

    def test_free_chat_uses_the_model_when_ready(self):
        model = FakeModel()
        make(self, model)
        reply = self.ask("i spent the whole afternoon repainting the garden fence")
        self.assertIn("proper adventure", reply)
        self.assertEqual(len(model.calls), 1)
        self.assertTrue(self.brain.in_conversation())

    def test_switched_off_uses_normal_lines(self):
        model = FakeModel()
        make(self, model, enabled=False)
        reply = self.ask("i spent the whole afternoon repainting the garden fence")
        self.assertTrue(reply)
        self.assertEqual(model.calls, [])

    def test_failure_and_bad_text_fall_back(self):
        for model in (FakeModel(fail=True), FakeModel(text="As an AI language model, I can't")):
            make(self, model)
            reply = self.ask("i spent the whole afternoon repainting the garden fence")
            self.assertTrue(reply)
            self.assertNotIn("language model", reply)

    def test_slow_model_times_out_and_falls_back(self):
        make(self, FakeModel(delay=1.0))
        self.settings.set("llm.max_seconds", 0.2)
        self.brain._vocab()                                   # the one-time word index is not part of the wait
        start = time.time()
        self.assertTrue(self.ask("i spent the whole afternoon repainting the garden fence"))
        self.assertLess(time.time() - start, 0.9)

    def test_crisis_and_commands_never_reach_the_model(self):
        model = FakeModel()
        make(self, model)
        self.ask("i want to kill myself")
        self.assertIsNone(self.ask("lower the lending gear"))
        self.assertEqual(model.calls, [])

    def test_known_shapes_keep_her_own_answers(self):
        model = FakeModel()
        make(self, model)
        self.ask("do you like pizza")
        self.assertEqual(model.calls, [])


class Download(unittest.TestCase):
    def test_http_refused(self):
        ok, _ = model_download.download("http://example.com/x.gguf", Path(tempfile.mkdtemp()) / "m.gguf")
        self.assertFalse(ok)

    def test_non_model_is_thrown_away(self):
        class Resp:
            headers = {"Content-Length": "0"}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n):
                if getattr(self, "done", False):
                    return b""
                self.done = True
                return b"<html>nope</html>"

        target = Path(tempfile.mkdtemp()) / "m.gguf"
        ok, message = model_download.download("https://x.test/m.gguf", target, opener=lambda url, timeout: Resp(), progress=lambda *_: None)
        self.assertFalse(ok)
        self.assertFalse(target.exists())
        self.assertFalse(target.with_name("m.gguf.part").exists())

    def test_model_check(self):
        folder = Path(tempfile.mkdtemp())
        small = folder / "a.gguf"
        small.write_bytes(b"GGUF" + b"0" * 100)
        self.assertFalse(model_download.looks_like_model(small))


if __name__ == "__main__":
    unittest.main()
