"""
THE ENGINE FOR THE SMALL AI MODEL - so Starling.exe can run it without any Python add-on.

Before 0.77.5 the AI chat needed llama-cpp-python, which only exists in a source install (setup.bat and a .venv folder), so
run_install_chat_model.bat could not work for people who use Starling.exe. Now:

  1. The "Install AI chat" button (Personality page) downloads llama.cpp's own ready-made Windows program, llama-server.exe,
     from its official GitHub releases (a CPU build, so the game keeps the graphics card), and the small model file.
  2. When she needs the model she starts llama-server.exe in the background, ONLY on this PC (127.0.0.1, a free port, no
     internet) and talks to it. After 10 idle minutes (or when Starling closes) the program is stopped and the memory is free.

Safety: HTTPS only, only the official ggml-org/llama.cpp release address, the zip must contain llama-server.exe and (when
GitHub gives a checksum) must match it, files are unpacked into a temporary folder with path checks, and nothing is kept
if anything looks wrong.
"""
import atexit
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from core import paths
from core.logger import get_logger
from core.secure_open import is_certificate_problem, open_url

log = get_logger("llm")

RELEASE_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
DOWNLOAD_PREFIX = "https://github.com/ggml-org/llama.cpp/releases/download/"
ASSET_RE = re.compile(r"^llama-[A-Za-z0-9._-]+-bin-win-cpu-x64\.zip$")       # the plain CPU build for 64-bit Windows
EXE_NAME = "llama-server.exe"
MIN_ZIP_BYTES = 2 * 1024 * 1024
MAX_ZIP_BYTES = 400 * 1024 * 1024
MAX_UNPACKED_BYTES = 1200 * 1024 * 1024
START_SECONDS = 90                 # a slow PC may need a while to load the model the first time
CREATE_NO_WINDOW = 0x08000000


def engine_dir():
    return paths.DATA_DIR / "llm" / "engine"


def engine_exe(folder=None):
    """The llama-server.exe that was installed, or None."""
    folder = Path(folder) if folder else engine_dir()
    try:
        if not folder.is_dir():
            return None
        found = sorted(folder.rglob(EXE_NAME))
        return found[0] if found else None
    except OSError:
        return None


def pick_asset(release):
    """(name, url, size, sha256 or '') of the Windows CPU zip in a GitHub release record, or None."""
    for asset in (release or {}).get("assets") or []:
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        if ASSET_RE.match(name) and url.startswith(DOWNLOAD_PREFIX) and url.endswith("/" + name):
            digest = str(asset.get("digest") or "")
            return name, url, int(asset.get("size") or 0), digest[7:] if digest.lower().startswith("sha256:") else ""
    return None


def _read_json(opener, url):
    request = urllib.request.Request(url, headers={"User-Agent": "Starling", "Accept": "application/vnd.github+json"})
    with opener(request, timeout=30) as response:
        raw = response.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise ValueError("The release answer was too big.")
    return json.loads(raw.decode("utf-8"))


def _safe_members(archive):
    """The zip entries that are safe to unpack (no absolute paths, no '..'), or None if any entry is not."""
    total = 0
    for info in archive.infolist():
        name = info.filename.replace("\\", "/")
        parts = PurePosixPath(name).parts
        if name.startswith("/") or ".." in parts or (parts and re.match(r"^[A-Za-z]:", parts[0])):
            return None
        total += info.file_size
    return archive.infolist() if total <= MAX_UNPACKED_BYTES else None


def install_engine(folder=None, opener=None, progress=print, platform_name=None):
    """Downloads and unpacks llama-server.exe. Returns (ok, message)."""
    if (platform_name or sys.platform) != "win32":
        return False, "The AI chat engine can only be installed on Windows."
    opener = opener or open_url                      # open_url retries once with the certifi certificate list (a common Windows problem)
    folder = Path(folder) if folder else engine_dir()
    if engine_exe(folder) is not None:
        return True, "The AI chat engine is already installed."
    temp = None
    part = None
    try:
        progress("Looking for the newest llama.cpp release on GitHub...")
        asset = pick_asset(_read_json(opener, RELEASE_API))
        if asset is None:
            return False, "I could not find the Windows CPU download in the latest llama.cpp release."
        name, url, size, sha256 = asset
        folder.parent.mkdir(parents=True, exist_ok=True)
        part = folder.parent / (name + ".part")
        digest = hashlib.sha256()
        progress("Downloading the engine (%s)..." % name)
        with opener(urllib.request.Request(url, headers={"User-Agent": "Starling"}), timeout=60) as response, open(part, "wb") as out:
            total = int(response.headers.get("Content-Length") or size or 0)
            done, shown = 0, -1
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if done > MAX_ZIP_BYTES:
                    raise ValueError("The download is bigger than expected.")
                percent = int(done * 100 / total) // 10 * 10 if total else done // (20 * 1024 * 1024)
                if percent != shown:
                    shown = percent
                    progress("  engine downloaded %d%s" % (percent, "%" if total else " x 20 MB"))
        if part.stat().st_size < MIN_ZIP_BYTES:
            return False, "The engine download was too small, so it was thrown away."
        if sha256 and digest.hexdigest().lower() != sha256.lower():
            return False, "The engine download did not match GitHub's checksum, so it was thrown away."
        if not zipfile.is_zipfile(part):
            return False, "The engine download was not a zip file, so it was thrown away."
        with zipfile.ZipFile(part) as archive:
            members = _safe_members(archive)
            if members is None:
                return False, "The engine zip had unsafe file names, so it was thrown away."
            if not any(m.filename.replace("\\", "/").split("/")[-1].lower() == EXE_NAME for m in members):
                return False, "The engine zip did not contain %s, so it was thrown away." % EXE_NAME
            temp = Path(tempfile.mkdtemp(prefix="engine_", dir=str(folder.parent)))
            archive.extractall(temp, members)
        if engine_exe(temp) is None:
            return False, "The engine could not be unpacked properly."
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
        os.replace(temp, folder)
        temp = None
        (folder / "VERSION.txt").write_text(name + "\n", encoding="utf-8")
        return True, "The AI chat engine is installed."
    except Exception as exc:
        log.exception("Installing the AI chat engine failed")
        if is_certificate_problem(exc) or is_certificate_problem(getattr(exc, "reason", None)):
            return False, ("Your PC does not trust GitHub's security certificate, so the download was refused. Antivirus 'web shield' or "
                           "'HTTPS scanning' is the usual cause: pause it for a few minutes, or allow Starling, and try again.")
        return False, "The engine download failed: %s" % exc
    finally:
        for leftover in (part,):
            try:
                if leftover is not None:
                    Path(leftover).unlink(missing_ok=True)
            except OSError:
                pass
        if temp is not None:
            shutil.rmtree(temp, ignore_errors=True)


def install_all(progress=print):
    """Engine first, then the model file. Returns (ok, message)."""
    ok, message = install_engine(progress=progress)
    if not ok:
        return False, message
    progress("Downloading the small chat model (about 400 MB)...")
    from core import model_download
    ok, message = model_download.download(progress=progress)
    if not ok:
        return False, message
    return True, "The AI chat is installed. It is switched on now."


class ServerModel:
    """llama-server.exe running quietly on this PC, with the same create_chat_completion() as llama-cpp-python's Llama."""

    def __init__(self, exe, model, threads=2, ctx=1024, popen=subprocess.Popen, opener=None, sleep=time.sleep,
                 clock=time.monotonic, start_seconds=START_SECONDS):
        self.exe, self.model, self.threads, self.ctx = Path(exe), Path(model), max(1, int(threads)), int(ctx)
        self._popen, self._sleep, self._clock, self.start_seconds = popen, sleep, clock, start_seconds
        self._opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({})).open       # never through a proxy: it is local
        self._process = None
        self.port = 0

    @staticmethod
    def free_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            return probe.getsockname()[1]

    def command(self):
        return [str(self.exe), "-m", str(self.model), "--host", "127.0.0.1", "--port", str(self.port), "-c", str(self.ctx),
                "-t", str(self.threads), "-np", "1", "--no-webui"]

    @staticmethod
    def _pid_file():
        return paths.DATA_DIR / "llm" / "server.pid"

    def _stop_leftover(self):
        """If Starling crashed last time, its engine may still be running. Stop it (only if the process really is llama-server.exe)."""
        if sys.platform != "win32":
            return
        try:
            pid = int(self._pid_file().read_text(encoding="utf-8").strip())
            subprocess.run(["taskkill", "/PID", str(pid), "/F", "/FI", "IMAGENAME eq " + EXE_NAME], capture_output=True, timeout=10,
                           creationflags=CREATE_NO_WINDOW)
            self._pid_file().unlink(missing_ok=True)
        except Exception:
            pass

    def start(self):
        """Starts the program and waits until it says it is ready. Raises RuntimeError if it cannot."""
        self._stop_leftover()
        self.port = self.free_port()
        flags = CREATE_NO_WINDOW if sys.platform == "win32" else 0
        log.info("Starting the AI chat engine on 127.0.0.1:%d (%d threads)", self.port, self.threads)
        self._process = self._popen(self.command(), cwd=str(self.exe.parent), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, creationflags=flags)
        atexit.register(self.close)
        try:
            self._pid_file().parent.mkdir(parents=True, exist_ok=True)
            self._pid_file().write_text(str(getattr(self._process, "pid", "")), encoding="utf-8")
        except OSError:
            pass
        deadline = self._clock() + self.start_seconds
        while self._clock() < deadline:
            if self._process.poll() is not None:
                code = self._process.poll()
                self._process = None
                raise RuntimeError("The AI chat engine stopped by itself (exit code %s). The model file may be damaged: install it again." % code)
            try:
                with self._opener("http://127.0.0.1:%d/health" % self.port, timeout=2) as response:
                    if getattr(response, "status", 200) == 200:
                        log.info("AI chat engine ready.")
                        return self
            except Exception:
                pass                                                         # 503 while the model loads: keep waiting
            self._sleep(0.5)
        self.close()
        raise RuntimeError("The AI chat engine did not become ready in %d seconds." % self.start_seconds)

    def create_chat_completion(self, messages, max_tokens=70, temperature=0.8, top_p=0.9, repeat_penalty=1.15, stop=None, **_ignored):
        body = json.dumps({"messages": messages, "max_tokens": max_tokens, "temperature": temperature, "top_p": top_p,
                           "repeat_penalty": repeat_penalty, "stop": stop or [], "stream": False}).encode("utf-8")
        request = urllib.request.Request("http://127.0.0.1:%d/v1/chat/completions" % self.port, data=body,
                                         headers={"Content-Type": "application/json"})
        with self._opener(request, timeout=40) as response:
            return json.loads(response.read().decode("utf-8"))

    def close(self):
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except Exception:
                    process.kill()
        except Exception:
            log.debug("Could not stop the AI chat engine cleanly", exc_info=True)
        try:
            self._pid_file().unlink(missing_ok=True)
        except OSError:
            pass
        log.info("AI chat engine stopped.")
