import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path

import numpy as np

from core.settings import Settings
from tts import kokoro_voice_setup as setup_mod
from tts.base_tts import BaseTTS, VoiceSettings
from tts.kokoro_tts import KokoroTTS, speed_from_rate, to_float32_array
from tts.speech_manager import SpeechManager

RATE = 24000


class FakeStream:
    def __init__(self, log, delay=0.0):
        self.log, self.delay, self.started, self.closed = log, delay, False, False

    def start(self):
        self.started = True

    def write(self, data):
        if self.delay:
            time.sleep(self.delay)
        self.log.append(data.copy())

    def stop(self):
        pass

    def close(self):
        self.closed = True


class FakeSound:
    def __init__(self, delay=0.0):
        self.written, self.delay, self.made = [], delay, []

    def OutputStream(self, samplerate, channels, dtype):
        assert (samplerate, channels, dtype) == (RATE, 1, "float32")
        stream = FakeStream(self.written, self.delay)
        self.made.append(stream)
        return stream


class FakePipeline:
    """Yields one second of 0.5 per sentence, like Kokoro's generator."""

    def __init__(self):
        self.calls = []

    def __call__(self, text, voice=None, speed=1.0):
        self.calls.append((text, voice, speed))
        for _ in text.split("."):
            if _.strip():
                yield (None, None, np.full(RATE // 2, 0.5, dtype=np.float32))


def ok_setup(pack, ref):
    return True, "fine"


def make(setup=ok_setup, sound=None, pipeline=None, **kw):
    pipe = pipeline or FakePipeline()
    tts = KokoroTTS(Path("x.pt"), Path("x.mp3"), pipeline_factory=lambda: pipe,
                    torch_load=lambda p: "PACK", sound_module=sound or FakeSound(),
                    setup_function=setup, **kw)
    return tts, pipe


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_resample_changes_length(self):
        out = setup_mod.resample(np.sin(np.linspace(0, 100, 44100)).astype(np.float32), 44100, 24000)
        self.assertEqual(out.size, 24000)

    def test_prepare_makes_mono_trimmed(self):
        stereo = np.zeros((44100 * 40, 2), dtype=np.float32) + 0.1
        out = setup_mod.prepare_reference(stereo, 44100)
        self.assertEqual(out.ndim, 1)
        self.assertLessEqual(out.size / RATE, 30.0)

    def test_too_short_is_refused(self):
        with self.assertRaises(setup_mod.VoiceSetupError):
            setup_mod.prepare_reference(np.zeros(RATE, dtype=np.float32), RATE)

    def test_wav_written_correctly(self):
        p = self.dir / "a.wav"
        setup_mod.write_wav(p, np.zeros(RATE, dtype=np.float32))
        with wave.open(str(p)) as w:
            self.assertEqual((w.getnchannels(), w.getframerate()), (1, RATE))

    def test_existing_pack_skips_everything(self):
        pack = self.dir / "custom_covas.pt"
        pack.write_bytes(b"data")
        ok, msg = setup_mod.ensure_custom_voice(pack, self.dir / "missing.mp3",
                                                reader=lambda p: 1 / 0, enroller=lambda p: 1 / 0)
        self.assertTrue(ok)

    def test_missing_recording_is_reported_not_raised(self):
        ok, msg = setup_mod.ensure_custom_voice(self.dir / "c.pt", self.dir / "none.mp3")
        self.assertFalse(ok)
        self.assertIn("not found", msg)

    def test_tuning_runs_once_and_saves(self):
        mp3 = self.dir / "r.mp3"
        mp3.write_bytes(b"x")
        saved = []
        calls = []

        def saver(tensor, path):
            Path(path).write_bytes(b"tensor")
            saved.append(tensor)

        def enroller(wav):
            calls.append(wav)
            self.assertTrue(Path(wav).is_file())
            return "TENSOR"

        reader = lambda p: (np.zeros((RATE * 10, 2), dtype=np.float32) + 0.1, RATE)
        pack = self.dir / "custom_covas.pt"
        ok, _ = setup_mod.ensure_custom_voice(pack, mp3, reader, enroller, saver)
        self.assertTrue(ok)
        self.assertEqual(saved, ["TENSOR"])
        self.assertTrue(pack.is_file())
        self.assertFalse(list(self.dir.glob("*.tmp")))
        self.assertFalse(list(self.dir.glob("*.wav")))
        ok, _ = setup_mod.ensure_custom_voice(pack, mp3, reader, enroller, saver)
        self.assertEqual(len(calls), 1)  # second boot skipped

    def test_enroller_crash_is_contained(self):
        mp3 = self.dir / "r.mp3"
        mp3.write_bytes(b"x")
        reader = lambda p: (np.zeros(RATE * 10, dtype=np.float32), RATE)
        with self.assertLogs("starling.kokoro_setup", level="ERROR"):
            ok, msg = setup_mod.ensure_custom_voice(self.dir / "c.pt", mp3, reader, lambda w: 1 / 0)
        self.assertFalse(ok)
        self.assertFalse((self.dir / "c.pt").exists())

    def test_extract_tensor_shapes(self):
        self.assertEqual(setup_mod._extract_tensor({"pack": 5}), 5)
        self.assertEqual(setup_mod._extract_tensor((7, 8)), 7)
        self.assertEqual(setup_mod._extract_tensor(9), 9)


class KokoroTests(unittest.TestCase):
    def test_speed_mapping(self):
        self.assertEqual(speed_from_rate(0), 1.0)
        self.assertGreater(speed_from_rate(10), 1.0)
        self.assertEqual(speed_from_rate("bad"), 1.0)

    def test_audio_conversion_handles_formats(self):
        arr = np.ones(4, dtype=np.float64)
        self.assertEqual(to_float32_array(arr).dtype, np.float32)
        self.assertEqual(to_float32_array((None, None, arr)).size, 4)

        class R:
            audio = arr
        self.assertEqual(to_float32_array(R()).size, 4)

    def test_not_started_is_unavailable_then_available(self):
        tts, _ = make()
        self.assertFalse(tts.available()[0])
        tts.start_loading()
        self.assertTrue(tts.wait_until_loaded(5))
        self.assertTrue(tts.available()[0])

    def test_failed_setup_marks_unavailable(self):
        tts, _ = make(setup=lambda p, r: (False, "no recording"))
        tts.start_loading()
        self.assertFalse(tts.wait_until_loaded(5))
        ok, why = tts.available()
        self.assertFalse(ok)
        self.assertIn("no recording", why)

    def test_speak_streams_float32_at_24k_with_voice_pack(self):
        sound = FakeSound()
        tts, pipe = make(sound=sound)
        tts.start_loading()
        tts.wait_until_loaded(5)
        pipe.calls.clear()
        self.assertTrue(tts.speak("One. Two.", VoiceSettings(volume=50)))
        self.assertEqual(pipe.calls[0][1], "PACK")
        data = np.concatenate(sound.written)
        self.assertEqual(data.size, RATE)            # 2 sentences x 0.5 s
        self.assertEqual(data.dtype, np.float32)
        self.assertAlmostEqual(float(data.max()), 0.25, places=4)   # volume 50%
        self.assertTrue(sound.made[0].closed)

    def test_stop_cuts_speech_off(self):
        sound = FakeSound(delay=0.05)
        tts, _ = make(sound=sound)
        tts.start_loading()
        tts.wait_until_loaded(5)
        result = []
        t = threading.Thread(target=lambda: result.append(tts.speak("a. b. c. d. e.", VoiceSettings())))
        t.start()
        time.sleep(0.3)
        tts.stop()
        t.join(5)
        self.assertFalse(t.is_alive())
        self.assertTrue(result[0])
        self.assertLess(sum(c.size for c in sound.written), RATE * 2)
        # and the next line is not suppressed by the old stop
        sound2 = tts.speak("Hello.", VoiceSettings())
        self.assertTrue(sound2)

    def test_line_waits_for_loading_then_speaks(self):
        gate = threading.Event()
        pipe = FakePipeline()
        tts = KokoroTTS(Path("x.pt"), Path("x.mp3"),
                        pipeline_factory=lambda: (gate.wait(5), pipe)[1],
                        torch_load=lambda p: "PACK", sound_module=FakeSound(), setup_function=ok_setup)
        tts.start_loading()
        threading.Timer(0.3, gate.set).start()
        self.assertTrue(tts.speak("Hi.", VoiceSettings()))

    def test_line_dropped_if_engine_never_loads(self):
        tts, _ = make(setup=lambda p, r: (False, "broken"))
        tts.start_loading()
        self.assertFalse(tts.speak("Hi.", VoiceSettings()))

    def test_pipeline_error_returns_false(self):
        class Bad:
            def __call__(self, *a, **k):
                if a[0] == "Ready.":
                    return iter(())
                raise RuntimeError("boom")
        tts, _ = make(pipeline=Bad())
        tts.start_loading()
        tts.wait_until_loaded(5)
        with self.assertLogs("starling.kokoro", level="ERROR"):
            self.assertFalse(tts.speak("Hi.", VoiceSettings()))

    def test_empty_text_does_nothing(self):
        tts, _ = make()
        self.assertFalse(tts.speak("", VoiceSettings()))


class Fake(BaseTTS):
    def __init__(self, name):
        self.name, self.label, self.spoken = name, name, []

    def available(self):
        return True, ""

    def speak(self, text, voice, audio_path=None):
        self.spoken.append(text)
        return True


class RoutingTests(unittest.TestCase):
    def manager(self, **values):
        s = Settings(Path(tempfile.gettempdir()) / "nope_kokoro.json").load()
        for k, v in values.items():
            s.set(k.replace("__", "."), v)
        return SpeechManager({"kokoro": Fake("kokoro"), "windows": Fake("windows")}, s)

    def test_old_windows_setting_now_means_kokoro(self):
        m = self.manager(tts__provider="windows")
        self.assertEqual(m.text_provider().name, "kokoro")

    def test_windows_only_when_opted_in_and_chosen(self):
        m = self.manager(tts__provider="windows", speech__windows_emergency_voice=True)
        self.assertEqual(m.text_provider().name, "windows")

    def test_windows_is_last_resort_when_opted_in(self):
        m = self.manager(speech__windows_emergency_voice=True)
        m.providers["kokoro"].available = lambda: (False, "down")
        self.assertEqual(m.text_provider().name, "windows")

    def test_no_windows_without_opt_in(self):
        m = self.manager()
        m.providers["kokoro"].available = lambda: (False, "down")
        self.assertIsNone(m.text_provider())


if __name__ == "__main__":
    unittest.main()


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "p.pt").write_bytes(b"pack")

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, pipe=None):
        pipe = pipe or FakePipeline()
        sound = FakeSound()
        tts = KokoroTTS(self.dir / "p.pt", self.dir / "r.mp3", pipeline_factory=lambda: pipe,
                        torch_load=lambda p: "PACK", sound_module=sound, setup_function=ok_setup,
                        cache_dir=self.dir / "cache")
        tts.start_loading()
        tts.wait_until_loaded(5)
        pipe.calls.clear()
        return tts, pipe, sound

    def test_second_time_a_line_is_played_from_the_cache(self):
        tts, pipe, sound = self.build()
        self.assertTrue(tts.speak("Hello there.", VoiceSettings()))
        self.assertEqual(len(pipe.calls), 1)
        self.assertEqual(len(list((self.dir / "cache").glob("*.npy"))), 1)
        sound.written.clear()
        self.assertTrue(tts.speak("Hello there.", VoiceSettings(volume=100)))
        self.assertEqual(len(pipe.calls), 1)            # not generated again
        data = np.concatenate(sound.written)
        self.assertEqual(data.size, RATE // 2)
        self.assertAlmostEqual(float(data.max()), 0.5, places=3)

    def test_retuned_voice_does_not_reuse_old_sound(self):
        tts, pipe, _ = self.build()
        tts.speak("Hello there.", VoiceSettings())
        (self.dir / "p.pt").write_bytes(b"a different voice pack")
        tts.speak("Hello there.", VoiceSettings())
        self.assertEqual(len(pipe.calls), 2)

    def test_render_fills_the_cache_without_playing(self):
        tts, pipe, sound = self.build()
        self.assertTrue(tts.render("Silent line."))
        self.assertEqual(sound.written, [])
        self.assertTrue(tts.render("Silent line."))
        self.assertEqual(len(pipe.calls), 1)

    def test_cut_off_line_is_not_cached(self):
        tts, pipe, sound = self.build()
        sound.delay = 0.05
        sound_stream_delay = 0.05
        tts._sound_module = FakeSound(delay=sound_stream_delay)
        t = threading.Thread(target=lambda: tts.speak(". ".join("s%d" % i for i in range(30)) + ".", VoiceSettings()))
        t.start()
        time.sleep(0.2)
        tts.stop()
        t.join(5)
        self.assertEqual(list((self.dir / "cache").glob("*.npy")), [])


class CacheBuilderTests(unittest.TestCase):
    def test_collects_fixed_lines_only(self):
        from personality.dialogue import DialogueManager
        from core import paths
        from tts.voice_cache_builder import collect_texts
        d = DialogueManager(paths.VOICEPACKS_DIR / "default").load()
        texts = collect_texts(d)
        self.assertGreater(len(texts), 300)
        self.assertEqual(len(texts), len(set(texts)))
        self.assertFalse([t for t in texts if "{" in t])
        mature = {l.text for ls in d.lines.values() for l in ls if l.mature and "{" not in l.text}
        self.assertEqual(set(texts) & mature, set())
        self.assertTrue(mature <= set(collect_texts(d, allow_mature=True)))


class CountdownTests(unittest.TestCase):
    def test_each_number_starts_just_under_one_second_after_the_last(self):
        sound = FakeSound()
        tts, pipe = make(sound=sound)
        tts.start_loading()
        tts.wait_until_loaded(5)
        pipe.calls.clear()
        self.assertTrue(tts.speak("Four.||Three.||Two.||One.||Engage.", VoiceSettings()))
        self.assertEqual([c[0] for c in pipe.calls], ["Four.", "Three.", "Two.", "One.", "Engage."])
        data = np.concatenate(sound.written)
        loud = np.abs(data) > 0.01
        starts = [i for i in range(1, data.size) if loud[i] and not loud[i - 1]]
        starts = [0] + starts if loud[0] else starts
        gaps = np.diff(starts) / float(RATE)
        self.assertEqual(len(starts), 5)
        for gap in gaps:
            self.assertGreater(gap, 0.85)
            self.assertLess(gap, 1.0)

    def test_long_words_never_get_a_negative_gap(self):
        class Long(FakePipeline):
            def __call__(self, text, voice=None, speed=1.0):
                yield (None, None, np.full(RATE * 2, 0.5, dtype=np.float32))
        sound = FakeSound()
        tts, _ = make(sound=sound, pipeline=Long())
        tts.start_loading()
        tts.wait_until_loaded(5)
        sound.written.clear()
        self.assertTrue(tts.speak("a||b", VoiceSettings()))
        self.assertGreater(np.concatenate(sound.written).size, RATE * 4)

    def test_parts_are_cached_separately_and_replay_with_the_same_timing(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / "p.pt").write_bytes(b"x")
            pipe = FakePipeline()
            sound = FakeSound()
            tts = KokoroTTS(folder / "p.pt", folder / "r.mp3", pipeline_factory=lambda: pipe,
                            torch_load=lambda p: "PACK", sound_module=sound, setup_function=ok_setup,
                            cache_dir=folder / "c")
            tts.start_loading()
            tts.wait_until_loaded(5)
            tts.speak("Four.||Three.", VoiceSettings())
            first = np.concatenate(sound.written).size
            pipe.calls.clear()
            sound.written.clear()
            tts.speak("Four.||Three.", VoiceSettings())
            self.assertEqual(pipe.calls, [])
            self.assertAlmostEqual(np.concatenate(sound.written).size, first, delta=RATE // 20)

    def test_other_voices_never_read_the_beat_marker_aloud(self):
        s = Settings(Path(tempfile.gettempdir()) / "nope_beat.json").load()
        s.set("speech.windows_emergency_voice", True)
        s.set("tts.provider", "windows")
        win = Fake("windows")
        m = SpeechManager({"kokoro": Fake("kokoro_down"), "windows": win}, s)
        m.providers["kokoro"].name = "kokoro"
        m.providers["kokoro"].available = lambda: (False, "down")
        m.start()
        try:
            m.say(text="Four.||Three.", priority="normal")
            m.wait_until_idle(5)
        finally:
            m.stop()
        self.assertEqual(win.spoken, ["Four. Three."])


class BuiltInVoiceTests(unittest.TestCase):
    def test_built_in_voice_is_used_and_default_is_cloned(self):
        tts, pipe = make()
        tts.start_loading(); tts.wait_until_loaded(5)
        tts.speak("Hello there.", VoiceSettings(voice="am_adam"))
        tts.speak("Hello again.", VoiceSettings(voice=""))
        tts.speak("Odd one.", VoiceSettings(voice="not_a_voice"))
        voices = [v for t, v, s in pipe.calls if t != "Ready."]
        self.assertEqual(voices, ["am_adam", "PACK", "PACK"])

    def test_cache_is_separate_per_voice(self):
        with tempfile.TemporaryDirectory() as d:
            tts, pipe = make(cache_dir=d)
            tts.start_loading(); tts.wait_until_loaded(5)
            for name in ("", "af_bella", "af_bella"):
                tts.speak("Same line.", VoiceSettings(voice=name))
            made = [c for c in pipe.calls if c[0] == "Same line."]
            self.assertEqual(len(made), 2)   # cloned once, bella once; second bella came from the cache

    def test_failed_built_in_voice_falls_back_to_cloned(self):
        class Picky(FakePipeline):
            def __call__(self, text, voice=None, speed=1.0):
                if voice == "af_sky":
                    raise RuntimeError("download failed")
                return super().__call__(text, voice, speed)
        tts, pipe = make(pipeline=Picky())
        tts.start_loading(); tts.wait_until_loaded(5)
        self.assertTrue(tts.speak("Fallback line.", VoiceSettings(voice="af_sky")))

    def test_dashboard_lists_female_and_male(self):
        from ui.settings_model import VOICES
        labels = [l for l, _ in VOICES]
        self.assertTrue(any("female" in l for l in labels) and any(l.endswith("- male") for l in labels))
        self.assertEqual(VOICES[0][1], "")
