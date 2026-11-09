import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from tts import melo_voice
from tts.base_tts import VoiceSettings
from tts.kokoro_tts import BUILT_IN_VOICES, KokoroTTS


class FakeModel:
    def __init__(self, speakers=None):
        self.hps = SimpleNamespace(data=SimpleNamespace(spk2id=speakers or {"EN-US": 0, "EN-BR": 1, "EN_INDIA": 2, "EN-AU": 3, "EN-Default": 4}, sampling_rate=44100))
        self.calls = []

    def tts_to_file(self, text, speaker, output_path, speed=1.0):
        self.calls.append((text, speaker, output_path, speed))
        return np.sin(np.linspace(0, 200, 44100)).astype(np.float32)           # one second of sound at 44100 Hz


class Sound:
    class OutputStream:
        written = []

        def __init__(self, **kw):
            pass

        def start(self):
            pass

        def write(self, chunk):
            Sound.OutputStream.written.append(len(chunk))

        def stop(self):
            pass

        def close(self):
            pass


class MeloTests(unittest.TestCase):
    def test_the_voice_is_in_the_voice_list(self):
        self.assertIn(melo_voice.VOICE_NAME, BUILT_IN_VOICES)

    def test_resampling_changes_the_length_to_24000_hz(self):
        out = melo_voice.resample(np.ones(44100, dtype=np.float32), 44100)
        self.assertAlmostEqual(out.size, 24000, delta=2)
        self.assertEqual(out.dtype, np.float32)
        same = melo_voice.resample(np.ones(100, dtype=np.float32), 24000)
        self.assertEqual(same.size, 100)
        self.assertEqual(melo_voice.resample(np.zeros(0, dtype=np.float32), 44100).size, 0)

    def test_the_engine_uses_the_australian_speaker_and_speed(self):
        model = FakeModel()
        engine = melo_voice.MeloEngine(lambda: model)
        pieces = list(engine("Hello there.", voice="melo_en_au", speed=1.2))
        self.assertEqual(len(pieces), 1)
        self.assertAlmostEqual(pieces[0].size, 24000, delta=2)
        self.assertEqual(model.calls[0], ("Hello there.", 3, None, 1.2))

    def test_a_model_without_the_australian_speaker_is_a_clear_error(self):
        engine = melo_voice.MeloEngine(lambda: FakeModel({"EN-US": 0}))
        with self.assertRaises(RuntimeError) as caught:
            list(engine("Hi."))
        self.assertIn("EN-AU", str(caught.exception))

    def test_without_the_package_she_falls_back_to_her_normal_voice(self):
        """MeloTTS is not installed here: choosing the Australian voice must still end with her speaking in the normal one."""
        with tempfile.TemporaryDirectory() as tmp:
            played = []

            class Pipeline:
                def __call__(self_inner, text, voice=None, speed=1.0):
                    played.append(voice)
                    yield np.ones(2400, dtype=np.float32) * 0.1
            tts = KokoroTTS(Path(tmp) / "p.pt", Path(tmp) / "r.mp3", pipeline_factory=lambda: Pipeline(),
                            torch_load=lambda path: "CLONED", sound_module=Sound, setup_function=lambda a, b: (True, "ok"))
            tts.start_loading()
            tts.wait_until_loaded(10)
            tts._pipeline_factory = None                         # behave like the real app: Melo really is missing
            tts.pipeline = Pipeline()
            self.assertFalse(melo_voice.is_installed())
            ok = tts.speak("Hello commander.", VoiceSettings(voice="melo_en_au"))
            self.assertTrue(ok)
            self.assertEqual(played[-1], "CLONED")               # the cloned voice spoke

    def test_with_a_fake_model_the_whole_speak_path_and_cache_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = FakeModel()

            class Pipeline:
                def __call__(self_inner, *a, **k):
                    return iter(())
            tts = KokoroTTS(Path(tmp) / "p.pt", Path(tmp) / "r.mp3", pipeline_factory=lambda: Pipeline(),
                            torch_load=lambda path: "CLONED", sound_module=Sound, setup_function=lambda a, b: (True, "ok"),
                            cache_dir=Path(tmp) / "cache")
            tts._melo_factory = lambda: model
            tts.start_loading()
            tts.wait_until_loaded(10)
            Sound.OutputStream.written = []
            self.assertTrue(tts.speak("Welcome aboard, commander.", VoiceSettings(voice="melo_en_au")))
            self.assertEqual(len(model.calls), 1)
            self.assertGreater(sum(Sound.OutputStream.written), 20000)
            self.assertTrue(tts.is_cached("Welcome aboard, commander."))
            self.assertTrue(tts.speak("Welcome aboard, commander.", VoiceSettings(voice="melo_en_au")))
            self.assertEqual(len(model.calls), 1)                 # the second time came from the saved line
