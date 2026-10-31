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
        self.assertIn("Install AI chat", llm.status())

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


# ---------------------------------------------------------------- 0.77.5: the downloaded engine (llama-server.exe)
import hashlib
import io
import json
import zipfile

from personality import llm_server


def make_zip(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class Reply:
    def __init__(self, data, status=200):
        self.data, self.status, self.pos = data, status, 0
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        if n is None or n < 0:
            n = len(self.data)
        chunk = self.data[self.pos:self.pos + n]
        self.pos += len(chunk)
        return chunk


def release_for(name, payload, digest=True, url=None):
    asset = {"name": name, "size": len(payload), "browser_download_url": url or (llm_server.DOWNLOAD_PREFIX + "b9999/" + name)}
    if digest:
        asset["digest"] = "sha256:" + hashlib.sha256(payload).hexdigest()
    return {"tag_name": "b9999", "assets": [asset]}


class EngineInstallTests(unittest.TestCase):
    NAME = "llama-b9999-bin-win-cpu-x64.zip"

    def run_install(self, payload, release=None, platform_name="win32"):
        folder = Path(tempfile.mkdtemp()) / "engine"
        release = release or release_for(self.NAME, payload)

        def opener(request, timeout=None):
            url = request if isinstance(request, str) else request.full_url
            return Reply(json.dumps(release).encode()) if url == llm_server.RELEASE_API else Reply(payload)
        return folder, llm_server.install_engine(folder, opener=opener, progress=lambda *_: None, platform_name=platform_name)

    def good_zip(self):
        return make_zip({"llama-server.exe": b"MZ" + b"0" * (3 * 1024 * 1024), "ggml-cpu.dll": b"x"})

    def test_picks_only_the_windows_cpu_x64_zip(self):
        names = ["llama-b1-bin-win-cuda-12.4-x64.zip", "llama-b1-bin-win-cpu-arm64.zip", "llama-b1-bin-win-vulkan-x64.zip",
                 "llama-b1-bin-ubuntu-x64.tar.gz", "llama-b1-bin-win-cpu-x64.zip"]
        release = {"assets": [{"name": n, "browser_download_url": llm_server.DOWNLOAD_PREFIX + "b1/" + n, "size": 1} for n in names]}
        self.assertEqual(llm_server.pick_asset(release)[0], "llama-b1-bin-win-cpu-x64.zip")
        self.assertIsNone(llm_server.pick_asset({"assets": []}))

    def test_refuses_a_download_from_somewhere_else(self):
        release = {"assets": [{"name": self.NAME, "browser_download_url": "https://evil.test/" + self.NAME, "size": 1}]}
        self.assertIsNone(llm_server.pick_asset(release))

    def test_installs_unpacks_and_finds_the_exe(self):
        folder, (ok, message) = self.run_install(self.good_zip())
        self.assertTrue(ok, message)
        self.assertIsNotNone(llm_server.engine_exe(folder))
        self.assertTrue((folder / "VERSION.txt").is_file())

    def test_already_installed_is_not_downloaded_again(self):
        folder, (ok, _m) = self.run_install(self.good_zip())
        ok2, message = llm_server.install_engine(folder, opener=lambda *a, **k: self.fail("downloaded again"), progress=lambda *_: None, platform_name="win32")
        self.assertTrue(ok2)

    def test_wrong_checksum_is_thrown_away(self):
        payload = self.good_zip()
        release = release_for(self.NAME, payload)
        release["assets"][0]["digest"] = "sha256:" + "0" * 64
        folder, (ok, message) = self.run_install(payload, release)
        self.assertFalse(ok)
        self.assertIn("checksum", message)
        self.assertIsNone(llm_server.engine_exe(folder))

    def test_not_a_zip_and_no_exe_and_unsafe_names_are_refused(self):
        for payload in (b"<html>" + b"0" * (3 * 1024 * 1024), make_zip({"readme.txt": b"0" * (3 * 1024 * 1024)}),
                        make_zip({"../evil.exe": b"0" * (3 * 1024 * 1024), "llama-server.exe": b"x"})):
            folder, (ok, _message) = self.run_install(payload)
            self.assertFalse(ok)
            self.assertFalse(folder.exists())
            self.assertEqual(list(folder.parent.glob("*.part")), [])

    def test_too_small_is_refused(self):
        folder, (ok, _m) = self.run_install(make_zip({"llama-server.exe": b"x"}))
        self.assertFalse(ok)

    def test_only_on_windows(self):
        _folder, (ok, message) = self.run_install(self.good_zip(), platform_name="linux")
        self.assertFalse(ok)
        self.assertIn("Windows", message)


class FakeProcess:
    pid = 4242

    def __init__(self, exits=None):
        self.exits, self.terminated, self.killed = exits, False, False

    def poll(self):
        return self.exits if not self.terminated else 0

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True


class ServerModelTests(unittest.TestCase):
    def make(self, process=None, health_after=1, answer="Hello there, Commander."):
        process = process or FakeProcess()
        calls = {"health": 0, "chat": []}

        def opener(request, timeout=None):
            url = request if isinstance(request, str) else request.full_url
            if url.endswith("/health"):
                calls["health"] += 1
                if calls["health"] <= health_after:
                    raise OSError("503 loading")
                return Reply(b'{"status": "ok"}')
            calls["chat"].append(json.loads(request.data.decode()))
            return Reply(json.dumps({"choices": [{"message": {"content": answer}}]}).encode())
        ticks = iter(x * 0.5 for x in range(10000))
        model = llm_server.ServerModel(Path("llama-server.exe"), Path("m.gguf"), 3, popen=lambda *a, **k: process, opener=opener,
                                       sleep=lambda s: None, clock=lambda: next(ticks), start_seconds=30)
        return model, process, calls

    def test_starts_waits_for_ready_and_answers_like_llama_cpp(self):
        model, process, calls = self.make()
        model.start()
        out = model.create_chat_completion(messages=[{"role": "user", "content": "hi"}], max_tokens=20, stop=["\n\n"], temperature=0.8)
        self.assertEqual(out["choices"][0]["message"]["content"], "Hello there, Commander.")
        self.assertEqual(calls["chat"][0]["max_tokens"], 20)
        self.assertGreaterEqual(calls["health"], 2)
        model.close()
        self.assertTrue(process.terminated)

    def test_command_is_local_only(self):
        model, _p, _c = self.make()
        model.port = 5555
        command = model.command()
        self.assertEqual(command[command.index("--host") + 1], "127.0.0.1")
        self.assertIn("--no-webui", command)
        self.assertEqual(command[command.index("-t") + 1], "3")

    def test_a_program_that_exits_is_reported(self):
        model, _p, _c = self.make(process=FakeProcess(exits=1))
        with self.assertRaises(RuntimeError):
            model.start()

    def test_never_ready_gives_up_and_stops_it(self):
        model, process, _c = self.make(health_after=10 ** 6)
        with self.assertRaises(RuntimeError):
            model.start()
        self.assertTrue(process.terminated)


class LocalLLMEngineTests(Base):
    def test_uses_the_downloaded_engine_and_stops_it_on_unload(self):
        class Engine:
            started = closed = 0

            def __init__(self, exe, model, threads):
                self.model = FakeModel()

            def start(self):
                Engine.started += 1
                return self

            def create_chat_completion(self, **kw):
                return self.model.create_chat_completion(**kw)

            def close(self):
                Engine.closed += 1
        folder = Path(tempfile.mkdtemp())
        modelfile = folder / "m.gguf"
        modelfile.write_bytes(b"GGUF")
        self.settings.set("llm.enabled", True)
        self.settings.set("llm.model_file", str(modelfile))
        llm = LocalLLM(self.settings, engine_finder=lambda: Path("llama-server.exe"), server_factory=Engine)
        self.assertTrue(llm.ready())
        messages = build_messages("tell me about your day please", "Friendly")
        self.assertIsNotNone(llm.reply(messages))
        self.assertEqual(Engine.started, 1)
        llm.unload()
        self.assertEqual(Engine.closed, 1)

    def test_says_what_to_press_when_nothing_is_installed(self):
        self.settings.set("llm.enabled", True)
        llm = LocalLLM(self.settings, engine_finder=lambda: None)
        llm._import_ok = False
        self.assertIn("Install AI chat", llm.status())
        ok, message = llm.test()
        self.assertFalse(ok)
        self.assertIn("Install AI chat", message)

    def test_test_button_reports_a_working_model(self):
        llm = LocalLLM(self.settings, loader=lambda path, threads: FakeModel())
        ok, message = llm.test()
        self.assertTrue(ok, message)
        self.assertIn("It works", message)
        llm = LocalLLM(self.settings, loader=lambda path, threads: FakeModel(fail=True))
        ok, message = llm.test()
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------- 0.77.7: GitHub certificate not trusted on some PCs
import ssl
import urllib.error

from core import secure_open


class CertificateRetryTests(unittest.TestCase):
    def failing_then_ok(self, calls):
        def opener(request, timeout=None, context=None):
            calls.append(context)
            if context is None:
                raise urllib.error.URLError(ssl.SSLCertVerificationError("unable to get issuer certificate"))
            return "reply"
        return opener

    def test_retries_once_with_the_certifi_list_and_still_checks_the_certificate(self):
        calls = []
        original = secure_open.certifi_context
        secure_open.certifi_context = lambda: "fake-context"
        try:
            self.assertEqual(secure_open.open_url("https://x.test/a", 5, opener=self.failing_then_ok(calls)), "reply")
        finally:
            secure_open.certifi_context = original
        self.assertEqual(calls, [None, "fake-context"])

    def test_other_errors_are_not_retried(self):
        calls = []

        def opener(request, timeout=None, context=None):
            calls.append(context)
            raise urllib.error.URLError(OSError("no internet"))
        with self.assertRaises(urllib.error.URLError):
            secure_open.open_url("https://x.test/a", 5, opener=opener)
        self.assertEqual(calls, [None])

    def test_without_certifi_the_original_error_is_raised(self):
        original = secure_open.certifi_context
        secure_open.certifi_context = lambda: None
        try:
            with self.assertRaises(urllib.error.URLError):
                secure_open.open_url("https://x.test/a", 5, opener=self.failing_then_ok([]))
        finally:
            secure_open.certifi_context = original

    def test_install_explains_a_certificate_problem_in_plain_words(self):
        def opener(request, timeout=None):
            raise urllib.error.URLError(ssl.SSLCertVerificationError("unable to get issuer certificate"))
        ok, message = llm_server.install_engine(Path(tempfile.mkdtemp()) / "engine", opener=opener, progress=lambda *_: None, platform_name="win32")
        self.assertFalse(ok)
        self.assertIn("security certificate", message)
        self.assertIn("Antivirus", message)

    def test_the_engine_and_model_downloads_use_the_retrying_opener(self):
        import inspect
        self.assertIs(model_download.download.__defaults__[2], secure_open.open_url)
        self.assertIn("open_url", inspect.getsource(llm_server.install_engine))


class FindAssetTests(unittest.TestCase):
    NAME = "llama-b9999-bin-win-cpu-x64.zip"

    def opener_for(self, answers, page_url=None):
        """answers: {url: python object to send as JSON}. page_url: where the plain release page redirects to."""
        def opener(request, timeout=None):
            url = request if isinstance(request, str) else request.full_url
            if url == llm_server.RELEASE_PAGE:
                if page_url is None:
                    raise OSError("no page")
                reply = Reply(b"<html>")
                reply.geturl = lambda: page_url
                return reply
            if url not in answers:
                raise OSError("unexpected " + url)
            return Reply(json.dumps(answers[url]).encode())
        return opener

    def good(self, tag="b9999"):
        name = "llama-%s-bin-win-cpu-x64.zip" % tag
        return {"tag_name": tag, "assets": [{"name": name, "size": 5, "browser_download_url": llm_server.DOWNLOAD_PREFIX + tag + "/" + name}]}

    def test_latest_release_is_used_when_it_has_the_file(self):
        found, _why = llm_server.find_asset(self.opener_for({llm_server.RELEASE_API: self.good()}))
        self.assertEqual(found[0], self.NAME)

    def test_falls_back_to_the_release_list_when_latest_has_no_files_yet(self):
        answers = {llm_server.RELEASE_API: {"tag_name": "b10000", "assets": []}, llm_server.RELEASE_LIST_API: [{"tag_name": "b10000", "assets": []}, self.good()]}
        found, _why = llm_server.find_asset(self.opener_for(answers))
        self.assertEqual(found[0], self.NAME)

    def test_falls_back_to_the_plain_release_page_when_the_api_is_limited(self):
        limited = {"message": "API rate limit exceeded for 1.2.3.4"}
        answers = {llm_server.RELEASE_API: limited, llm_server.RELEASE_LIST_API: limited}
        found, _why = llm_server.find_asset(self.opener_for(answers, page_url="https://github.com/ggml-org/llama.cpp/releases/tag/b8863"))
        self.assertEqual(found[0], "llama-b8863-bin-win-cpu-x64.zip")
        self.assertTrue(found[1].startswith(llm_server.DOWNLOAD_PREFIX + "b8863/"))

    def test_when_nothing_works_the_reason_is_in_the_message(self):
        answers = {llm_server.RELEASE_API: {"message": "API rate limit exceeded"}, llm_server.RELEASE_LIST_API: []}
        found, why = llm_server.find_asset(self.opener_for(answers))
        self.assertIsNone(found)
        self.assertIn("rate limit", why)

    def test_a_page_that_names_a_strange_tag_is_not_trusted(self):
        found, _why = llm_server.find_asset(self.opener_for({llm_server.RELEASE_API: {"assets": []}, llm_server.RELEASE_LIST_API: []},
                                                            page_url="https://github.com/ggml-org/llama.cpp/releases/tag/../../evil"))
        self.assertIsNone(found)
