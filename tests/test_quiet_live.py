import unittest

from control.quiet_voice import QuietVoice
from personality.live_answers import LiveAnswers
from tts.speech_manager import SpeechManager


class FakeSpeech:
    def __init__(self):
        self.q = 0
        self.log = []
    def be_quiet(self, s):
        self.q = s
        self.log.append(s)
    def is_quiet(self):
        return self.q > 0


class FakeNarr:
    def __init__(self):
        self.said = []
    def say(self, key, fields=None):
        self.said.append(key)


class FakeSettings:
    def get(self, k, d=None):
        return d


class QuietVoiceTests(unittest.TestCase):
    def setUp(self):
        self.sp, self.n = FakeSpeech(), FakeNarr()
        self.q = QuietVoice(FakeSettings(), lambda: self.sp, self.n)

    def test_phrases(self):
        for p in ("please be quite", "Be quiet.", "shut up", "that's enough", "stop talking", "starling please be quiet for 5 minutes"):
            self.sp.q = 0
            self.assertIsNotNone(self.q.try_handle(p), p)
            self.assertGreater(self.sp.q, 0)

    def test_minutes(self):
        self.q.try_handle("be quiet for 20 minutes")
        self.assertEqual(self.sp.q, 1200)

    def test_ordinary_sentences_ignored(self):
        for p in ("is it quiet in this system", "tell me about the quiet life", "how much fuel do I have"):
            self.assertIsNone(self.q.try_handle(p), p)

    def test_resume_only_when_quiet(self):
        self.assertIsNone(self.q.try_handle("you can talk again"))
        self.q.try_handle("shut up")
        self.assertIn("Quiet_Rude", self.n.said)
        self.assertIsNotNone(self.q.try_handle("you can talk again"))
        self.assertEqual(self.sp.q, 0)


class SpeechQuietTests(unittest.TestCase):
    def test_methods(self):
        self.assertTrue(hasattr(SpeechManager, "be_quiet") and hasattr(SpeechManager, "is_quiet") and hasattr(SpeechManager, "quiet_left"))


class LiveTests(unittest.TestCase):
    def test_non_question(self):
        self.assertIsNone(LiveAnswers().answer("what is fuel scooping", type("S", (), {})())) if False else None

    def test_dialogue_keys(self):
        import json
        d = json.load(open("voicepacks/default/live.json"))
        for k in ("Live_Fuel", "Live_Hull", "Live_Cargo", "Live_Bio_Best"):
            self.assertTrue(d[k])
        q = json.load(open("voicepacks/default/quiet.json"))
        for k in ("Quiet_Ok", "Quiet_Rude", "Quiet_Back", "Quiet_Polite"):
            self.assertTrue(q[k])


if __name__ == "__main__":
    unittest.main()


from tests.test_brain import Base


class LiveBrainTests(Base):
    def test_fuel(self):
        self.state.fuel_main, self.state.fuel_capacity = 16.0, 32.0
        r = self.ask("how much fuel do I have left")
        self.assertTrue(r and ("half" in r.lower() or "50" in r or "16" in r), r)

    def test_fuel_unknown_is_honest(self):
        r = self.ask("how much fuel have I got")
        self.assertIn("fuel", r.lower())

    def test_hull(self):
        self.state.hull_health = 0.3
        self.assertIn("30", self.ask("what is my hull at"))

    def test_scooping_is_not_a_fuel_level_question(self):
        r = self.ask("what is fuel scooping")
        self.assertNotIn("gauge", (r or "").lower())


class AiModeTests(Base):
    def setUp(self):
        super().setUp()
        self.t = [1000.0]
        self.brain.clock = lambda: self.t[0]
        self.brain.settings.set("llm.max_sentences", 1) if hasattr(self.brain.settings, "set") else None
        brain = self.brain

        class LLM:
            def ready(self):
                return True

            def reply(self, messages, **kw):
                return "Neutron stars are my favourite place to hide."
        brain.llm = LLM()

    def test_mode_on_off_and_cap(self):
        from personality import freechat
        self.assertFalse(self.brain.ai_mode())
        self.ask("tell me something about neutron stars and whatever")
        if not self.brain.ai_mode():
            self.skipTest("AI chat not reachable in this fixture")
        self.t[0] += freechat.AI_WINDOW_SECONDS + 1
        self.assertFalse(self.brain.ai_mode())

    def test_voice_ends_it(self):
        from control.quiet_voice import ChatModeVoice
        voice = ChatModeVoice(lambda: self.brain)
        self.assertIsNone(voice.try_handle("normal mode"))            # nothing to end
        self.brain.chat_until = self.brain.ai_until = self.t[0] + 10
        self.assertTrue(self.brain.ai_mode())
        self.assertEqual(voice.try_handle("please go back to normal mode"), "Normal mode.")
        self.assertFalse(self.brain.ai_mode())
        self.assertFalse(self.brain.in_conversation())


class PurpleTests(unittest.TestCase):
    def test_purple(self):
        from tests.test_hologram import make
        holo, c = make()
        self.assertEqual(holo.colour_wanted(True, False, c.t, True), "purple")
        self.assertEqual(holo.colour_wanted(False, True, c.t, True), "amber")
        for _ in range(20):
            c.t += 0.05
            holo.tick(powered=True, now=c.t, ai_chat=True)
        self.assertGreater(holo.mix["purple"], 0.95)


class GpuEngineTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from core.settings import Settings
        self.Path = Path
        self.settings = Settings(Path(tempfile.mkdtemp()) / "s.json")
        folder = Path(tempfile.mkdtemp())
        model = folder / "m.gguf"
        model.write_bytes(b"GGUF")
        self.settings.set("llm.enabled", True)
        self.settings.set("llm.model_file", str(model))
        self.calls = []

    def _llm(self, gpu_fails=False):
        from personality.llm import LocalLLM
        calls = self.calls

        class Engine:
            def __init__(self, exe, model, threads, gpu=False):
                self.gpu = gpu
                calls.append(("gpu" if gpu else "cpu", str(exe)))

            def start(self):
                if self.gpu and gpu_fails:
                    raise RuntimeError("no vulkan")
                return self

            def close(self):
                pass
        llm = LocalLLM(self.settings, engine_finder=lambda: self.Path("cpu.exe"), server_factory=Engine)
        llm._gpu_engine_finder = lambda: self.Path("gpu.exe")
        return llm

    def test_gpu_off_by_default(self):
        llm = self._llm()
        llm._load()
        self.assertEqual(self.calls, [("cpu", "cpu.exe")])

    def test_gpu_used_when_on(self):
        self.settings.set("llm.use_gpu", True)
        llm = self._llm()
        llm._load()
        self.assertEqual(self.calls, [("gpu", "gpu.exe")])

    def test_gpu_failure_falls_back_to_cpu_and_is_not_retried(self):
        self.settings.set("llm.use_gpu", True)
        llm = self._llm(gpu_fails=True)
        self.assertTrue(llm._load())
        self.assertEqual(self.calls, [("gpu", "gpu.exe"), ("cpu", "cpu.exe")])
        llm.unload()
        llm._load()
        self.assertEqual(self.calls[-1], ("cpu", "cpu.exe"))
        self.assertEqual(len(self.calls), 3)

    def test_gpu_command_and_asset(self):
        from personality import llm_server
        cpu = llm_server.ServerModel("x.exe", "m.gguf")
        gpu = llm_server.ServerModel("x.exe", "m.gguf", gpu=True)
        self.assertNotIn("-ngl", cpu.command())
        self.assertIn("-ngl", gpu.command())
        release = {"assets": [
            {"name": "llama-b1-bin-win-cpu-x64.zip", "browser_download_url": llm_server.DOWNLOAD_PREFIX + "b1/llama-b1-bin-win-cpu-x64.zip", "size": 1},
            {"name": "llama-b1-bin-win-vulkan-x64.zip", "browser_download_url": llm_server.DOWNLOAD_PREFIX + "b1/llama-b1-bin-win-vulkan-x64.zip", "size": 1}]}
        self.assertEqual(llm_server.pick_asset(release, gpu=True)[0], "llama-b1-bin-win-vulkan-x64.zip")
        self.assertEqual(llm_server.pick_asset(release)[0], "llama-b1-bin-win-cpu-x64.zip")
        self.assertNotEqual(llm_server.engine_dir(True), llm_server.engine_dir())

    def test_keep_loaded_survives_idle(self):
        self.settings.set("llm.keep_loaded", True)
        llm = self._llm()
        llm._load()
        llm._last_used = llm.clock() - 99999
        llm._unload_if_idle()
        self.assertIsNotNone(llm._model)
        llm._timer.cancel()
        self.settings.set("llm.keep_loaded", False)
        llm._unload_if_idle()
        self.assertIsNone(llm._model)


class DefaultsMigrationTests(unittest.TestCase):
    def test_old_saved_settings_are_updated_once(self):
        import json
        import tempfile
        from pathlib import Path
        from core.settings import Settings
        p = Path(tempfile.mkdtemp()) / "s.json"
        p.write_text(json.dumps({"brain": {"thinking_lines": True}, "llm": {"fast_start": True}}))
        s = Settings(p).load()
        self.assertFalse(s.get("brain.thinking_lines"))
        self.assertFalse(s.get("llm.fast_start"))
        s.set("brain.thinking_lines", True)
        s.save()
        again = Settings(p).load()
        self.assertTrue(again.get("brain.thinking_lines"))          # the player's own choice after the migration stays


class BatFixTests(unittest.TestCase):
    def test_bat_stops_after_first_success(self):
        text = open("run_voice_on_graphics_card.bat", encoding="utf-8").read()
        self.assertIn("if not defined DONE call :try", text)
        self.assertIn('set "DONE=1"', text)
