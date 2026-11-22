import random
import unittest

from streaming import intro as I
from streaming.chat import ChatMessage


class Settings(dict):
    def get(self, key, default=None):
        return dict.get(self, key, default)


class Rig:
    def __init__(self, ai=None, enabled=True, free=True):
        self.t = 0.0
        self.keys, self.texts, self.events = [], [], []
        self.is_free = free
        s = Settings({"streaming.enabled": enabled, "streaming.intro_wait": 60, "streaming.intro_minutes": 10})
        self.intro = I.StreamIntro(s, lambda k, f=None: self.keys.append((k, f)), self.texts.append, ai, lambda: self.is_free,
                                   self.events.append, lambda: self.t, random.Random(1))

    def msg(self, text, user="Gav"):
        return self.intro.offer(ChatMessage("twitch", user, text))

    def run(self, seconds):
        out = []
        end = self.t + seconds
        while self.t < end:
            self.t += 1.0
            r = self.intro.pump()
            if r:
                out.append(r)
        return out


class IntroTests(unittest.TestCase):
    def test_needs_chat_on(self):
        self.assertEqual(Rig(enabled=False).intro.start(), "off")

    def test_start_twice(self):
        r = Rig()
        self.assertEqual(r.intro.start(), "started")
        self.assertEqual(r.intro.start(), "running")

    def test_quiet_minute_then_begin(self):
        r = Rig()
        r.intro.start()
        self.msg = r.msg
        r.msg("hello there")
        self.assertEqual(r.run(55), [])
        self.assertEqual(r.keys, [])
        self.assertIn("began", r.run(10))
        self.assertEqual(r.keys[0][0], "StreamIntro_Begin")

    def test_answers_with_ai_and_adds_name(self):
        r = Rig(ai=lambda m: "welcome to the show")
        r.intro.start()
        r.run(61)
        r.msg("hi starling")
        r.run(10)
        self.assertTrue(r.texts and r.texts[0].lower().startswith("gav"))

    def test_every_reply_mentions_what_she_is_doing_and_acts_it(self):
        seen = []
        r = Rig(ai=lambda m: seen.append(m[0]["content"]) or "hello")
        r.intro.start()
        r.run(61)
        before = len(r.events)
        r.msg("hi starling")
        r.run(12)
        self.assertEqual(len(seen), 1)
        self.assertIn(r.intro.activity, seen[0])
        self.assertIn("ALWAYS", seen[0])
        self.assertGreater(len(r.events), before)           # the hologram was told to play a clip

    def test_falls_back_to_lines(self):
        r = Rig(ai=lambda m: None)
        r.intro.start()
        r.run(61)
        r.msg("hi starling")
        r.run(10)
        self.assertEqual(r.texts, [])
        self.assertIn("StreamIntro_Reply", [k for k, _ in r.keys])

    def test_commands_not_taken(self):
        r = Rig()
        r.intro.start()
        self.assertFalse(r.msg("!starling what is a neutron star"))

    def test_filters(self):
        r = Rig()
        r.intro.start()
        r.run(61)
        r.msg("look http://spam.com")
        r.msg("x" * 300)
        r.msg("hi", user="Nightbot")
        self.assertEqual(len(r.intro.queue), 0)

    def test_waits_when_busy(self):
        r = Rig(ai=lambda m: "hello")
        r.intro.start()
        r.run(61)
        r.is_free = False
        r.msg("hi")
        r.run(20)
        self.assertEqual(r.texts, [])
        r.is_free = True
        r.run(10)
        self.assertEqual(len(r.texts), 1)

    def test_filler_when_quiet(self):
        r = Rig()
        r.intro.start()
        r.run(61)
        r.run(120)
        self.assertIn("StreamIntro_Filler", [k for k, _ in r.keys])

    def test_ends_and_stops_answering(self):
        r = Rig()
        r.intro.start()
        out = r.run(600)
        self.assertIn("ended", out)
        self.assertFalse(r.intro.running)
        self.assertFalse(r.msg("hi"))
        self.assertEqual(r.keys[-1][0], "StreamIntro_End")

    def test_cancel(self):
        r = Rig()
        self.assertFalse(r.intro.cancel())
        r.intro.start()
        self.assertTrue(r.intro.cancel())
        self.assertEqual(r.run(100), [])


class VoiceTests(unittest.TestCase):
    def make(self):
        r = Rig()
        said = []

        class N:
            def say(self, key, fields=None):
                said.append(key)
        return r, I.IntroVoice(lambda: r.intro, N()), said

    def test_minutes(self):
        self.assertEqual(I.minutes_in("start a five minute intro"), 5)
        self.assertEqual(I.minutes_in("start ten minit intro"), 10)
        self.assertIsNone(I.minutes_in("start the intro"))

    def test_start_and_stop(self):
        r, v, said = self.make()
        self.assertIsNotNone(v.try_handle("Start ten minute intro"))
        self.assertTrue(r.intro.running)
        self.assertEqual(said[-1], "StreamIntro_Start")
        v.try_handle("start the intro")
        self.assertEqual(said[-1], "StreamIntro_Already")
        self.assertIsNotNone(v.try_handle("I'm ready"))
        self.assertFalse(r.intro.running)

    def test_ordinary_talk_ignored(self):
        r, v, said = self.make()
        for s in ("i'm ready", "stop the intro", "start a timer for ten minutes", "what is the intro cost", "start my ten minute stream"):
            self.assertIsNone(v.try_handle(s), s)
        self.assertEqual(said, [])

    def test_chat_off(self):
        r = Rig(enabled=False)
        said = []

        class N:
            def say(self, key, fields=None):
                said.append(key)
        v = I.IntroVoice(lambda: r.intro, N())
        v.try_handle("start ten minute intro")
        self.assertEqual(said, ["StreamIntro_NoChat"])


if __name__ == "__main__":
    unittest.main()
