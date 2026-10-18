"""The Watcher bridge: she answers him in her mood, and makes him wait for a calm moment."""

import unittest

from control.voidcompass import VoidError
from personality.watcher import HOLD_MAX_SECONDS, REPLY_START_DELAY_SECONDS, WatcherBridge
from core.event_bus import EventBus
from journal.game_state import GameState
from tests.test_commands import FakeSpeech
from tests.test_phase6b import dialogue, make_settings


class FakeClient:
    def __init__(self):
        self.said, self.stopped, self.speaking, self.error = [], 0, False, None

    def voice(self):
        if self.error:
            raise self.error
        return {"speaking": self.speaking}

    def voice_stop(self):
        self.stopped += 1

    def voice_say(self, text):
        self.said.append(text)


class BusyAfterSay(FakeSpeech):
    busy = False

    def is_busy(self):
        return self.busy


class Heard:
    def __init__(self, text="The star is cold.", who="watcher"):
        self.item = {"type": "voice", "data": {"text": text, "from": who}}


class WatcherTests(unittest.TestCase):
    def build(self, mood="Friendly", **values):
        values.setdefault("personality__mood", mood)
        values.setdefault("personality__mood_mode", "fixed")
        self.settings = make_settings(**values)
        self.client, self.speech, self.state = FakeClient(), BusyAfterSay(), GameState()
        self.now = [100.0]
        self.ask = type("A", (), {"pending": None})()
        self.bridge = WatcherBridge(EventBus(), self.speech, dialogue(), self.settings, self.client,
                                    state_provider=lambda: self.state, ask_provider=lambda: self.ask,
                                    clock=lambda: self.now[0], sleep=lambda s: None)
        self.bridge.rng.random = lambda: 0.0          # always answer
        return self.bridge

    def hear(self, *args, **kw):
        self.bridge.handle(Heard(*args, **kw).item)

    def finish_and_reply(self):
        self.now[0] += REPLY_START_DELAY_SECONDS + 0.1
        self.bridge.tick()

    def spoken(self):
        return [s["text"] for s in self.speech.said]

    # ---- replies in her mood ----
    def test_replies_after_he_finishes(self):
        self.build("Friendly")
        self.hear()
        self.bridge.tick()
        self.assertEqual(self.spoken(), [])                    # not yet: his voice may still be starting
        self.finish_and_reply()
        self.assertEqual(len(self.spoken()), 1)
        self.assertEqual(self.client.stopped, 0)

    def test_waits_while_he_is_still_talking(self):
        self.build()
        self.hear()
        self.client.speaking = True
        self.finish_and_reply()
        self.assertEqual(self.spoken(), [])
        self.client.speaking = False
        self.bridge.tick()
        self.assertEqual(len(self.spoken()), 1)

    def test_every_mood_has_its_own_lines(self):
        pool = dialogue()
        for mood in ("Close", "Friendly", "Neutral", "Sarcastic", "Frustrated"):
            self.assertGreaterEqual(len(pool.pool("WatcherReply_" + mood, "", False, False)), 10, mood)

    def test_good_mood_is_kind_and_bad_mood_is_rude(self):
        pool = dialogue()
        kind = {l.text for m in ("Close", "Friendly") for l in pool.pool("WatcherReply_" + m, "", True, False)}
        rude = {l.text for m in ("Sarcastic", "Frustrated") for l in pool.pool("WatcherReply_" + m, "", True, False)}
        self.assertFalse(kind & rude)
        self.assertTrue(any("shut up" in t.lower() or "quiet" in t.lower() for t in rude))
        self.assertFalse(any("shut up" in t.lower() for t in kind))

    def test_strong_language_only_when_allowed(self):
        pool = dialogue()
        clean = {l.text for l in pool.pool("WatcherReply_Frustrated", "", False, False)}
        full = {l.text for l in pool.pool("WatcherReply_Frustrated", "", True, False)}
        self.assertTrue(clean < full)
        self.assertFalse(any("fuck" in t.lower() or "hell" in t.lower() for t in clean))

    def test_uses_current_mood(self):
        self.build("Frustrated")
        self.hear()
        self.finish_and_reply()
        text = self.spoken()[0]
        self.assertIn(text, {l.text for l in dialogue().pool("WatcherReply_Frustrated", "", False, False)} |
                      {l.text.replace("{player}", "") for l in dialogue().pool("WatcherReply_Frustrated", "", False, False)})

    def test_reply_setting_never(self):
        self.build(watcher__reply="never")
        self.bridge.rng.random = lambda: 0.5
        self.hear()
        self.finish_and_reply()
        self.assertEqual(self.spoken(), [])

    def test_switched_off(self):
        self.build(watcher__enabled=False)
        self.hear()
        self.finish_and_reply()
        self.assertEqual((self.spoken(), self.client.stopped), ([], 0))

    def test_ignores_other_voices(self):
        self.build()
        self.hear(who="api")
        self.finish_and_reply()
        self.assertEqual(self.spoken(), [])

    # ---- waiting for a calm moment ----
    def test_busy_speech_holds_him(self):
        self.build()
        self.speech.busy = True
        self.hear("Hull at ninety percent.")
        self.assertEqual(self.client.stopped, 1)
        self.bridge.tick()
        self.assertEqual(self.client.said, [])                 # still busy
        self.speech.busy = False
        self.bridge.tick()
        self.assertEqual(self.client.said, ["Hull at ninety percent."])
        self.finish_and_reply()
        self.assertEqual(len(self.spoken()), 1)                # and she answers him after he says it

    def test_each_dangerous_state_holds_him(self):
        for bit in (6, 17, 19, 20, 22, 23, 30):
            self.build()
            self.state.status_flags = 1 << bit
            self.hear()
            self.assertEqual(self.client.stopped, 1, bit)
            self.state.status_flags = 0
            self.bridge.tick()
            self.assertEqual(len(self.client.said), 1, bit)

    def test_open_question_holds_him(self):
        self.build()
        self.ask.pending = object()
        self.hear()
        self.assertEqual(self.client.stopped, 1)
        self.ask.pending = None
        self.bridge.tick()
        self.assertEqual(len(self.client.said), 1)

    def test_critical_event_holds_him_for_a_while(self):
        self.build()
        self.bridge._last_critical = self.now[0]
        self.hear()
        self.assertEqual(self.client.stopped, 1)
        self.now[0] += 31
        self.bridge.tick()
        self.assertEqual(len(self.client.said), 1)

    def test_stale_line_is_dropped(self):
        self.build()
        self.speech.busy = True
        self.hear()
        self.now[0] += HOLD_MAX_SECONDS + 1
        self.speech.busy = False
        self.bridge.tick()
        self.assertEqual(self.client.said, [])
        self.assertIsNone(self.bridge.held)

    def test_no_reply_while_in_trouble(self):
        self.build()
        self.hear()
        self.state.status_flags = 1 << 6
        self.finish_and_reply()
        self.assertEqual(self.spoken(), [])

    def test_waiting_can_be_switched_off(self):
        self.build(watcher__wait_for_calm=False)
        self.speech.busy = True
        self.hear()
        self.assertEqual(self.client.stopped, 0)

    def test_void_compass_errors_do_not_crash(self):
        self.build()
        self.hear()
        self.client.error = VoidError("offline")
        self.finish_and_reply()
        self.assertEqual(self.spoken(), [])


class LoopTests(unittest.TestCase):
    def test_client_events_url(self):
        from control.voidcompass import VoidCompass
        seen = []

        class R:
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def read(s): return b'{"seq": 7, "events": []}'

        def opener(request, timeout=None):
            seen.append((request.full_url, timeout))
            return R()
        c = VoidCompass(opener=opener)
        self.assertEqual(c.events(5, "voice", 20)["seq"], 7)
        self.assertTrue(seen[0][0].endswith("/events?since=5&types=voice&wait=20"))
        self.assertGreater(seen[0][1], 20)
        self.assertEqual(c.now_seq(), 7)


if __name__ == "__main__":
    unittest.main()
