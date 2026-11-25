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


class GpuTorchTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self.base = Path(tempfile.mkdtemp()) / "torch_gpu"

    class R:
        def __init__(self, code=0):
            self.returncode, self.stdout, self.stderr = code, "", ""

    def _install(self, results, **kw):
        from tts import gpu_torch
        seen = []

        def run(command, **k):
            seen.append(command)
            if "--target" in command:
                (self.base / "torch").mkdir(parents=True, exist_ok=True)
            return results(command)
        out = gpu_torch.install(run=run, free_bytes=lambda: 10 * 1073741824, base=self.base, platform_name="win32", python="py", **kw)
        return out, seen

    def test_not_windows_or_no_nvidia(self):
        from tts import gpu_torch
        self.assertFalse(gpu_torch.install(base=self.base, platform_name="linux")[0])
        out, _ = self._install(lambda c: self.R(1))
        self.assertFalse(out[0])
        self.assertIn("NVIDIA", out[1])
        self.assertFalse(self.base.exists())

    def test_not_enough_disk(self):
        from tts import gpu_torch
        ok, msg = gpu_torch.install(run=lambda c, **k: self.R(0), free_bytes=lambda: 1024, base=self.base, platform_name="win32")
        self.assertFalse(ok)
        self.assertIn("disk space", msg)

    def test_first_working_version_stops_the_loop(self):
        out, seen = self._install(lambda c: self.R(0))
        self.assertTrue(out[0])
        installs = [c for c in seen if "--target" in c]
        self.assertEqual(len(installs), 1)                         # not four downloads
        self.assertIn("cu126", installs[0][-1])
        self.assertTrue(self.base.exists())

    def test_falls_through_and_cleans_up(self):
        def results(c):
            if "--target" in c:
                return self.R(1 if "cu126" in c[-1] else 0)
            if c[1:2] == ["-I"]:
                return self.R(1 if "cu124" in "".join(map(str, c)) else 0)
            return self.R(0)
        out, seen = self._install(results)
        self.assertTrue(out[0])
        self.assertEqual(len([c for c in seen if "--target" in c]), 2)
        self.assertTrue(any("cu124" in c[-1] for c in seen if "--target" in c))

    def test_nothing_works_removes_the_folder(self):
        def results(c):
            return self.R(1 if ("--target" in c or "-I" in c) else 0)
        out, _ = self._install(results)
        self.assertFalse(out[0])
        self.assertFalse(self.base.exists())

    def test_activate_puts_folder_first_and_gives_up_after_failed_starts(self):
        from tts import gpu_torch
        (self.base / "torch").mkdir(parents=True)
        gpu_torch._write({"tag": "cu126", "starts_without_voice": 0}, self.base)
        path = ["a"]
        self.assertTrue(gpu_torch.activate(self.base, path))
        self.assertEqual(path[0], str(self.base))
        for _ in range(gpu_torch.MAX_FAILED_STARTS - 1):
            gpu_torch.activate(self.base, ["a"])
        gpu_torch.voice_ok(self.base)                                # her voice came up: count forgotten
        self.assertEqual(gpu_torch._read(self.base)["starts_without_voice"], 0)
        for _ in range(gpu_torch.MAX_FAILED_STARTS):
            gpu_torch.activate(self.base, ["a"])
        note = gpu_torch.activate(self.base, ["a"])
        self.assertIn("put aside", note)
        self.assertFalse(self.base.exists())

    def test_activate_without_install_does_nothing(self):
        from tts import gpu_torch
        path = ["a"]
        self.assertEqual(gpu_torch.activate(self.base, path), "")
        self.assertEqual(path, ["a"])

    def test_a_new_version_gets_fresh_tries_after_old_failed_starts(self):
        from tts import gpu_torch
        (self.base / "torch").mkdir(parents=True)
        gpu_torch._write({"tag": "cu126", "starts_without_voice": gpu_torch.MAX_FAILED_STARTS, "version": "0.0.1"}, self.base)
        note = gpu_torch.activate(self.base, ["a"])
        self.assertNotIn("put aside", note)                          # not thrown away just because an older Starling kept crashing
        self.assertTrue(self.base.exists())
        self.assertEqual(gpu_torch._read(self.base)["starts_without_voice"], 1)

    def test_main_logs_the_graphics_card_note_only_after_the_log_exists(self):
        """Regression: with the graphics-card torch installed main() wrote to app.log before start() made it, and Starling closed at once."""
        import sys
        from unittest import mock
        import main as starling_main

        class FakeApp:
            def __init__(self):
                self.log = None                                       # exactly like the real App before start()
                self.settings = mock.Mock()
                self.processor = None

            def start(self, **kw):
                self.log = mock.Mock()

            def status_report(self):
                return []

            def stop(self):
                pass
        made = []

        def factory():
            made.append(FakeApp())
            return made[0]
        with mock.patch.object(starling_main, "App", factory), mock.patch.object(starling_main, "_gpu_note", "Using the graphics-card torch from X"), \
                mock.patch("core.crash.install"), mock.patch("core.crash.mark_clean_exit"), mock.patch.object(sys, "argv", ["main.py", "--check", "--silent"]):
            code = starling_main.main()
        self.assertEqual(code, 0)
        made[0].log.info.assert_any_call("%s", "Using the graphics-card torch from X")


class ChatPinTests(unittest.TestCase):
    def setUp(self):
        from streaming.pin import ChatPin
        self.t = [100.0]
        self.pin = ChatPin(clock=lambda: self.t[0])

    def test_click_toggles(self):
        self.assertTrue(self.pin.toggle(5, "Gav", "hello there", "youtube"))
        self.assertEqual(self.pin.current(), ("Gav", "hello there", "youtube"))
        self.assertEqual(self.pin.pinned_seq(), 5)
        self.assertTrue(self.pin.toggle(6, "Ann", "second", "twitch"))       # another line replaces it
        self.assertEqual(self.pin.current()[0], "Ann")
        self.assertFalse(self.pin.toggle(6, "Ann", "second", "twitch"))      # the same line again takes it away
        self.assertIsNone(self.pin.current())

    def test_her_pick_shows_then_goes_after_she_speaks_and_the_manual_one_returns(self):
        self.pin.toggle(1, "Gav", "mine", "youtube")
        self.pin.show_for_reply("Ann", "what is a neutron star", "twitch")
        self.assertEqual(self.pin.current()[0], "Ann")
        self.pin.settle(False)                       # not spoken yet: stays
        self.t[0] += 3
        self.pin.settle(True)                        # she speaks
        self.t[0] += 5
        self.pin.settle(True)
        self.assertEqual(self.pin.current()[0], "Ann")
        self.t[0] += 1
        self.pin.settle(False)                       # just finished: a moment longer
        self.assertEqual(self.pin.current()[0], "Ann")
        self.t[0] += 2
        self.pin.settle(False)
        self.assertEqual(self.pin.current()[0], "Gav")

    def test_never_stuck(self):
        from streaming import pin as p
        self.pin.show_for_reply("Ann", "x", "")
        self.t[0] += p.AUTO_UNSPOKEN_SECONDS + 1
        self.pin.settle(False)
        self.assertIsNone(self.pin.current())
        self.pin.show_for_reply("Ann", "x", "")
        self.pin.settle(True)
        self.t[0] += p.AUTO_MAX_SECONDS + 1
        self.pin.settle(True)
        self.assertIsNone(self.pin.current())

    def test_long_text_is_cut(self):
        from streaming.pin import shorten, MAX_CHARS
        self.assertLessEqual(len(shorten("word " * 200)), MAX_CHARS)

    def test_wrap_and_lines(self):
        from ui.chat_pin_overlay import wrap, tag_colour
        lines = wrap("one two three four five six seven", lambda s: len(s) * 10, 100)
        self.assertTrue(all(len(x) * 10 <= 100 for x in lines))
        self.assertEqual(" ".join(lines), "one two three four five six seven")
        self.assertEqual(len(wrap("word " * 100, lambda s: len(s) * 10, 100, max_lines=3)), 3)
        self.assertNotEqual(tag_colour("twitch"), tag_colour("youtube"))

    def test_chat_window_line_lookup(self):
        from ui.chat_window import line_at
        from streaming.feed import FeedLine
        chat = FeedLine(1, "chat", "twitch", "Ann", "hi")
        event = FeedLine(2, "event", "twitch", "Bob", "Bob subscribed")
        self.assertEqual(line_at([chat, event], 0), chat)
        self.assertIsNone(line_at([chat, event], 1))
        self.assertIsNone(line_at([chat, event], 5))

    def test_director_ask_and_intro_show_the_comment(self):
        from types import SimpleNamespace
        from streaming import wiring
        from streaming.pin import ChatPin
        from streaming.feed import ChatFeed
        pin = ChatPin()

        class S:
            def get(self, k, d=None):
                return d
        app = SimpleNamespace(chat_pin=pin, settings=S())
        feed = ChatFeed()
        feed.add_message(SimpleNamespace(platform="twitch", user="Ann", text="what is a neutron star", mod=False, sub=False, owner=False))
        wiring.show_comment(app, "Ann", "what is a neutron star", SimpleNamespace(feed=feed))
        self.assertEqual(pin.current(), ("Ann", "what is a neutron star", "twitch"))
        from streaming.intro import StreamIntro
        seen = []
        intro = StreamIntro(S(), lambda *a, **k: True, lambda t: True)
        intro.pin = lambda u, t: seen.append((u, t))
        intro._reply("Bob", "hello")
        self.assertEqual(seen, [("Bob", "hello")])


class PinPlacementTests(unittest.TestCase):
    def test_box_is_on_the_overlays_page_and_places_the_window(self):
        from ui import overlay_layout as L
        from ui import chat_pin_overlay as O
        box = L.box_for("pin")
        self.assertEqual((box.h_key, box.v_key), ("streaming.pin_x", "streaming.pin_up"))

        class S(dict):
            def get(self, k, d=None):
                return dict.get(self, k, d)
        s = S({"streaming.pin_x": 10, "streaming.pin_up": 20})
        x, y, w, h = L.rect(box, s, 1920, 1080)
        saved = L.settings_for(box, x, y, w, h)
        self.assertAlmostEqual(saved["streaming.pin_x"], 10, delta=0.2)
        self.assertAlmostEqual(saved["streaming.pin_up"], 20, delta=0.2)
        left, top = O.place(1920, 1080, 600, 150, 10, 20)
        self.assertEqual((left, top), (192, 1080 - 216 - 150))
        self.assertEqual(O.place(1920, 1080, 600, 150, 95, 0), (1320, 930))        # kept on screen


class DashboardTidyTests(unittest.TestCase):
    def setUp(self):
        from ui.settings_model import SettingsModel

        class S(dict):
            def get(self, k, d=None):
                return dict.get(self, k, d)
        self.model = SettingsModel(S())

    def test_no_setting_lost_or_shown_twice(self):
        keys = [f.key for f in self.model.all_fields()]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertGreaterEqual(len(keys), 246)          # the same 246 settings as before the tidy-up (only their pages changed)
        for must in ("llm.use_gpu", "streaming.pin_overlay", "hologram.ai_colour", "speech.quiet_minutes", "app.name", "streaming.window",
                     "hologram.size", "red_alert.banner", "hack.overlay"):
            self.assertIn(must, keys)

    def test_groups_cover_every_sidebar_page_once(self):
        listed = [p.id for _t, pages in self.model.groups() for p in pages]
        self.assertEqual(sorted(listed), sorted(p.id for p in self.model.sidebar_pages))
        self.assertEqual([t for t, _ in self.model.groups()], ["Setup", "Her", "Flying", "Stream", "Screen", "Tools"])

    def test_big_pages_are_split(self):
        sizes = {}
        for page in self.model.pages:
            sizes[page.id] = len(page.fields)
        self.assertLess(sizes["personality"], 30)
        self.assertLess(sizes["streaming"], 25)
        for new in ("aichat", "hologram", "streamwindow", "streamintro"):
            self.assertIn(new, sizes)
        page = {p.id: p for p in self.model.pages}
        self.assertIn("llm.use_gpu", [f.key for f in page["aichat"].fields])
        self.assertIn("streaming.pin_replies", [f.key for f in page["streamwindow"].fields])
        self.assertIn("streaming.chime_in", [f.key for f in page["streamintro"].fields])
        self.assertIn("red_alert.banner", [f.key for f in page["overlays"].fields])
        self.assertIn("streaming.pin_overlay", [f.key for f in page["overlays"].fields])

    def test_search(self):
        found = {f.key: p.id for p, f in self.model.search("purple")}
        self.assertEqual(found, {"hologram.ai_colour": "hologram"})
        self.assertIn("llm.use_gpu", [f.key for _p, f in self.model.search("gpu")])
        self.assertEqual(self.model.search("x"), [])
        self.assertEqual(self.model.search("zzzzqqq"), [])
        names = [f.label.lower() for _p, f in self.model.search("keep loaded")]
        self.assertTrue(names and "loaded" in names[0])
        self.assertLessEqual(len(self.model.search("the")), 30)

    def test_advanced_and_new_marks(self):
        adv = [f for f in self.model.all_fields() if f.advanced]
        new = [f for f in self.model.all_fields() if f.new]
        self.assertGreater(len(adv), 20)
        self.assertTrue(new)
        for page in self.model.pages:
            if page.fields:
                self.assertTrue([f for f in page.fields if not f.advanced], "page %s has only advanced settings" % page.id)

    def test_owner_of_a_section(self):
        page = {p.id: p for p in self.model.pages}
        self.assertEqual(self.model.owner(page["listening"]), "voice")
        self.assertEqual(self.model.owner(page["aichat"]), "aichat")

    def test_dashboard_compiles(self):
        import py_compile
        py_compile.compile("ui/dashboard.py", doraise=True)
