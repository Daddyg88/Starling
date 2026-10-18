import queue
import tempfile
import threading
import time
import unittest
from pathlib import Path

import numpy as np

from core.event_bus import EventBus
from core.settings import Settings
from personality.dialogue import DialogueManager
from personality.voice_replies import VoiceReplies
from stt.base_stt import BaseSTT
from stt.faster_whisper_stt import FasterWhisperSTT
from stt.listener import HEARD, Listener
from stt.microphone import MicrophoneStream, find_microphone, list_microphones
from stt.providers import build_stt_providers, choose_stt
from stt.vad import RATE, UtteranceDetector
from stt.wake import parse_wake
from core import paths

FRAME = 480


def quiet(n=1):
    return [np.random.default_rng(1).normal(0, 0.001, FRAME).astype(np.float32) for _ in range(n)]


def loud(n=1):
    t = np.arange(FRAME) / RATE
    return [(0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32) for _ in range(n)]


def feed_all(detector, frames):
    out = []
    for f in frames:
        r = detector.feed(f)
        if r is not None:
            out.append(r)
    return out


class DetectorTests(unittest.TestCase):
    def test_a_spoken_sentence_is_cut_out(self):
        d = UtteranceDetector()
        got = feed_all(d, quiet(45) + loud(20) + quiet(40))
        self.assertEqual(len(got), 1)
        self.assertGreater(got[0].size, 20 * FRAME)       # speech plus a little lead-in and tail

    def test_silence_gives_nothing(self):
        self.assertEqual(feed_all(UtteranceDetector(), quiet(200)), [])

    def test_a_tiny_click_is_ignored(self):
        self.assertEqual(feed_all(UtteranceDetector(), quiet(45) + loud(3) + quiet(40)), [])

    def test_a_long_ramble_is_cut_at_the_limit(self):
        d = UtteranceDetector(max_seconds=2.0)
        got = feed_all(d, quiet(45) + loud(200))
        self.assertGreaterEqual(len(got), 1)
        self.assertLessEqual(got[0].size, 2.1 * RATE)

    def test_two_sentences_are_two_utterances(self):
        got = feed_all(UtteranceDetector(), quiet(45) + loud(20) + quiet(40) + loud(20) + quiet(40))
        self.assertEqual(len(got), 2)

    def test_noisy_room_raises_the_bar(self):
        d = UtteranceDetector()
        noise = [np.random.default_rng(i).normal(0, 0.02, FRAME).astype(np.float32) for i in range(100)]
        feed_all(d, noise)
        self.assertGreater(d.threshold(), 0.04)

    def test_constant_hum_is_not_mistaken_for_speech(self):
        d = UtteranceDetector(max_seconds=2.0)
        hum = [np.random.default_rng(i).normal(0, 0.02, FRAME).astype(np.float32) for i in range(300)]
        got = feed_all(d, hum)
        self.assertEqual(got, [])

    def test_reset_forgets_half_heard_speech(self):
        d = UtteranceDetector()
        feed_all(d, quiet(45) + loud(10))
        d.reset()
        self.assertEqual(feed_all(d, quiet(40)), [])


class WakeTests(unittest.TestCase):
    def test_name_and_request(self):
        self.assertEqual(parse_wake("Hey Starling, open the galaxy map!"), (True, "open the galaxy map"))
        self.assertEqual(parse_wake("Starling open the galaxy map"), (True, "open the galaxy map"))

    def test_name_alone(self):
        self.assertEqual(parse_wake("Starling?"), (True, ""))

    def test_misheard_spellings_still_count(self):
        for heard in ("Star ling open the map", "Starlin what is the fuel", "Sterling, hello"):
            self.assertTrue(parse_wake(heard)[0], heard)

    def test_no_name(self):
        self.assertEqual(parse_wake("open the galaxy map"), (False, "open the galaxy map"))
        self.assertFalse(parse_wake("the fuel is low")[0])

    def test_empty(self):
        self.assertEqual(parse_wake(""), (False, ""))

    def test_other_wake_phrase(self):
        self.assertTrue(parse_wake("Computer, status", "Computer")[0])


class FakeMic:
    """Plays a list of frames, then silence."""

    def __init__(self, frames):
        self.frames = queue.Queue()
        for f in frames:
            self.frames.put(f)
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def read(self, timeout=0.5):
        try:
            return self.frames.get(timeout=0.01)
        except queue.Empty:
            time.sleep(0.01)
            return None

    def stop(self):
        self.stopped = True


class FakeSTT(BaseSTT):
    name = "fake"
    label = "fake"

    def __init__(self, text="Starling open the galaxy map", fail=False):
        self.text, self.fail, self.heard_audio = text, fail, []
        self.loaded = False

    def available(self):
        return True, ""

    def load(self):
        self.loaded = True

    def transcribe(self, audio):
        self.heard_audio.append(audio)
        if self.fail:
            raise RuntimeError("boom")
        return self.text


def settings(**values):
    s = Settings(Path(tempfile.gettempdir()) / "nope_stt.json").load()
    for k, v in values.items():
        s.set(k.replace("__", "."), v)
    return s


def wait_for(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


class ListenerTests(unittest.TestCase):
    def build(self, frames, stt=None, **settings_values):
        bus = EventBus()
        heard = []
        bus.subscribe(HEARD, heard.append)
        stt = stt or FakeSTT()
        mic = FakeMic(frames)
        listener = Listener(bus, stt, settings(**settings_values), lambda: mic)
        return listener, bus, heard, stt, mic

    def test_a_spoken_request_is_announced(self):
        listener, bus, heard, stt, mic = self.build(quiet(45) + loud(20) + quiet(40))
        listener.start()
        try:
            self.assertTrue(wait_for(lambda: heard))
        finally:
            listener.stop()
        self.assertTrue(stt.loaded)
        self.assertTrue(mic.started and mic.stopped)
        self.assertTrue(heard[0].data["wake"])
        self.assertEqual(heard[0].data["command"], "open the galaxy map")
        self.assertEqual(heard[0].priority, "normal")

    def test_she_does_not_hear_herself(self):
        listener, bus, heard, stt, mic = self.build([])
        listener.start()
        try:
            bus.publish("speech.started", {})
            for f in quiet(45) + loud(20) + quiet(40):
                mic.frames.put(f)
            time.sleep(0.6)
            self.assertEqual(stt.heard_audio, [])
        finally:
            listener.stop()

    def test_she_is_deaf_for_a_moment_after_speaking(self):
        now = [100.0]
        bus = EventBus()
        listener = Listener(bus, FakeSTT(), settings(), lambda: FakeMic([]), clock=lambda: now[0])
        bus.subscribe("speech.finished", listener._on_speech_finished)
        bus.publish("speech.finished", {})
        self.assertTrue(listener.deaf())
        now[0] += 1.0
        self.assertFalse(listener.deaf())

    def test_a_failed_transcription_does_not_stop_listening(self):
        listener, bus, heard, stt, mic = self.build(quiet(45) + loud(20) + quiet(40), stt=FakeSTT(fail=True))
        with self.assertLogs("starling.listener", level="ERROR"):
            listener.start()
            try:
                self.assertTrue(wait_for(lambda: stt.heard_audio))
                time.sleep(0.2)
            finally:
                listener.stop()
        self.assertEqual(heard, [])

    def test_a_missing_microphone_is_reported_not_a_crash(self):
        def broken():
            raise OSError("no microphone")
        listener = Listener(EventBus(), FakeSTT(), settings(), broken)
        with self.assertLogs("starling.listener", level="ERROR"):
            listener.start()
            wait_for(lambda: listener.failed_reason)
            listener.stop()
        self.assertIn("no microphone", listener.failed_reason)

    def test_junk_text_is_ignored(self):
        listener, bus, heard, *_ = self.build([])
        for junk in ("", "  ", ".", "a"):
            listener.handle_text(junk)
        self.assertEqual(heard, [])

    def test_wake_phrase_comes_from_settings(self):
        listener, bus, heard, *_ = self.build([], **{"stt__wake_phrase": "Computer"})
        listener.handle_text("Computer, status report")
        self.assertTrue(heard[0].data["wake"])
        self.assertEqual(heard[0].data["command"], "status report")


class FakeSpeech:
    def __init__(self):
        self.said = []

    def say(self, **kw):
        self.said.append(kw)
        return True


class ReplyTests(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.speech = FakeSpeech()
        self.dialogue = DialogueManager(paths.VOICEPACKS_DIR / "default").load()

    def replies(self, **values):
        r = VoiceReplies(self.bus, self.speech, self.dialogue, settings(**values))
        r.attach()
        return r

    def test_her_name_alone_gets_an_answer(self):
        self.replies()
        self.bus.publish(HEARD, {"text": "Starling", "wake": True, "command": ""})
        self.assertIn(self.speech.said[0]["text"], {l.text for l in self.dialogue.lines["WakeHeard"]})

    def test_a_request_is_acknowledged_honestly(self):
        self.replies()
        self.bus.publish(HEARD, {"text": "Starling open map", "wake": True, "command": "open map"})
        self.assertIn(self.speech.said[0]["text"], {l.text for l in self.dialogue.lines["CommandNotReady"]})

    def test_talking_without_her_name_is_ignored(self):
        self.replies()
        self.bus.publish(HEARD, {"text": "nice weather", "wake": False, "command": "nice weather"})
        self.assertEqual(self.speech.said, [])

    def test_replies_can_be_switched_off(self):
        self.replies(**{"stt__reply": False})
        self.bus.publish(HEARD, {"text": "Starling", "wake": True, "command": ""})
        self.assertEqual(self.speech.said, [])

    def test_speech_off_means_silence(self):
        self.replies(**{"speech__enabled": False})
        self.bus.publish(HEARD, {"text": "Starling", "wake": True, "command": ""})
        self.assertEqual(self.speech.said, [])


class FakeSound:
    def __init__(self, devices):
        self._devices = devices

    def query_devices(self):
        return self._devices


DEVICES = [{"name": "Speakers", "max_input_channels": 0}, {"name": "Headset Microphone (USB)", "max_input_channels": 1},
           {"name": "Webcam Mic", "max_input_channels": 2}]


class MicrophoneTests(unittest.TestCase):
    def test_only_recording_devices_are_listed(self):
        self.assertEqual(list_microphones(FakeSound(DEVICES)), [(1, "Headset Microphone (USB)"), (2, "Webcam Mic")])

    def test_find_by_part_of_the_name(self):
        self.assertEqual(find_microphone("headset", FakeSound(DEVICES)), 1)
        self.assertEqual(find_microphone("2", FakeSound(DEVICES)), 2)
        self.assertIsNone(find_microphone("", FakeSound(DEVICES)))
        with self.assertLogs("starling.microphone", level="WARNING"):
            self.assertIsNone(find_microphone("nothing like it", FakeSound(DEVICES)))

    def test_a_broken_sound_system_gives_an_empty_list(self):
        class Broken:
            def query_devices(self):
                raise OSError("no audio")
        with self.assertLogs("starling.microphone", level="WARNING"):
            self.assertEqual(list_microphones(Broken()), [])

    def test_stream_queues_blocks_and_never_piles_up(self):
        m = MicrophoneStream()
        for _ in range(500):
            m._callback(np.zeros((FRAME, 1), dtype=np.float32), FRAME, None, None)
        self.assertEqual(m.frames.qsize(), 200)
        self.assertGreater(m.overflows, 0)
        self.assertEqual(m.read().shape, (FRAME,))


class WhisperTests(unittest.TestCase):
    class Seg:
        def __init__(self, text):
            self.text = text

    class FakeModel:
        def __init__(self):
            self.calls = []

        def transcribe(self, audio, **kw):
            self.calls.append(kw)
            return iter([WhisperTests.Seg(" Starling,"), WhisperTests.Seg(" hello ")]), None

    def test_text_is_joined_and_options_are_light(self):
        model = self.FakeModel()
        stt = FasterWhisperSTT(model_factory=lambda: model)
        self.assertTrue(stt.available()[0])
        self.assertEqual(stt.transcribe(np.zeros(RATE, dtype=np.float32)), "Starling, hello")
        self.assertEqual(model.calls[0]["beam_size"], 1)
        self.assertEqual(model.calls[0]["language"], "en")

    def test_unavailable_without_the_package(self):
        import sys
        if "faster_whisper" in sys.modules:
            self.skipTest("installed here")
        ok, why = FasterWhisperSTT().available()
        self.assertFalse(ok)
        self.assertIn("setup.bat", why)

    def test_provider_choice_falls_back_to_faster_whisper(self):
        providers = build_stt_providers(settings())
        providers["faster_whisper"] = FasterWhisperSTT(model_factory=lambda: None)
        chosen = choose_stt(providers, settings(**{"stt__provider": "windows"}))
        self.assertEqual(chosen.name, "faster_whisper")

    def test_no_provider_gives_none(self):
        class Off(BaseSTT):
            name = "faster_whisper"
        self.assertIsNone(choose_stt({"faster_whisper": Off()}, settings()))


class SettingsTests(unittest.TestCase):
    def test_listening_is_off_by_default(self):
        s = settings()
        self.assertFalse(s.get("stt.enabled"))
        self.assertEqual(s.get("stt.provider"), "faster_whisper")
        self.assertTrue(s.get("stt.require_wake"))

    def test_voice_events_are_never_spoken_or_stored(self):
        from personality.speaker import _SKIP_PREFIXES
        self.assertIn("voice.", _SKIP_PREFIXES)


if __name__ == "__main__":
    unittest.main()
