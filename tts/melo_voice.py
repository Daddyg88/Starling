"""AUSTRALIAN VOICE (MeloTTS): an optional extra voice for her, picked in Settings > Voice as "Australian (MeloTTS)".

Why it is an extra voice and not a separate engine: it plugs into the same voice code as her Kokoro voices (tts/kokoro_tts.py), so the
saved-line cache, the voice warm-up, speed, volume and stopping all work exactly as before, and a line made once plays instantly next time.

MeloTTS is a free (MIT licence) offline voice that runs on the processor. Its English model has an Australian accent ("EN-AU").
It is NOT installed with her. The Voice page has a button "Install Australian voice" (tts/melo_install.py): it puts MeloTTS in its own
private folder data/melo_env and runs it as a separate program (tts/melo_worker.py), so it cannot break her. Delete that folder to remove it.
The install downloads several GB once, so it needs the internet.
If MeloTTS is missing or fails, she quietly uses her normal voice and says why in the log.
"""
import importlib.util
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from core.logger import get_logger

log = get_logger("melo")

VOICE_NAME = "melo_en_au"            # the name used in settings (tts.voice) and in the voice list
ACCENT = "EN-AU"                     # the speaker inside the MeloTTS English model
OUTPUT_RATE = 24000                  # the rate her sound code plays at (MeloTTS makes 44100)


def is_installed():
    """True when the Australian voice can be used: installed in its private folder (tts/melo_install.py) or MeloTTS is importable here."""
    try:
        from tts import melo_install
        if melo_install.is_installed():
            return True
    except Exception:
        pass
    try:
        return importlib.util.find_spec("melo") is not None
    except (ImportError, ValueError):
        return False


def resample(audio, source_rate, target_rate=OUTPUT_RATE):
    """Numpy float32 audio from one sample rate to another (simple and good enough for speech)."""
    import numpy as np
    audio = np.asarray(audio, dtype=np.float32).reshape(-1)
    if audio.size == 0 or int(source_rate) == int(target_rate):
        return audio
    try:
        from math import gcd
        from scipy.signal import resample_poly
        divisor = gcd(int(source_rate), int(target_rate))
        return resample_poly(audio, int(target_rate) // divisor, int(source_rate) // divisor).astype(np.float32)
    except Exception:                                    # no scipy: straight-line blending between samples
        length = max(1, int(round(audio.size * float(target_rate) / float(source_rate))))
        positions = np.linspace(0, audio.size - 1, length)
        return np.interp(positions, np.arange(audio.size), audio).astype(np.float32)


def _online_env():
    from tts.melo_install import online_env
    return online_env()


class MeloEngine:
    """Looks like Kokoro's engine: engine(text, voice=..., speed=...) gives pieces of sound at 24000 Hz.

    With the private install it talks to tts/melo_worker.py running in data/melo_env (started on first use, stopped after IDLE_SECONDS
    unused, restarted if it dies). With a model_factory (tests) or MeloTTS importable here, it runs in this program instead."""

    IDLE_SECONDS = 600
    LOAD_SECONDS = 300
    LINE_SECONDS = 120

    def __init__(self, model_factory=None, python=None, popen=subprocess.Popen, worker_args=(), idle_seconds=None, clock=time.monotonic):
        self._model_factory = model_factory
        self._python = python
        self._popen = popen
        self._worker_args = list(worker_args)
        self._clock = clock
        self.idle_seconds = self.IDLE_SECONDS if idle_seconds is None else idle_seconds
        self._model = None
        self._speaker = None
        self._rate = 44100
        self._lock = threading.Lock()
        self._process = None
        self._replies = None
        self._last_used = 0.0
        self._watch = None

    # ---- in this program (tests, or MeloTTS installed straight into Starling's own Python) ----
    def _load(self):
        with self._lock:
            if self._model is not None:
                return
            if self._model_factory is not None:
                model = self._model_factory()
            else:
                from melo.api import TTS                       # (imported only now: she starts fine without it)
                model = TTS(language="EN", device="cpu")
            speakers = dict(model.hps.data.spk2id)
            if ACCENT not in speakers:
                raise RuntimeError("this MeloTTS English model has no %s voice (it has %s)" % (ACCENT, ", ".join(sorted(speakers))))
            self._speaker = speakers[ACCENT]
            self._rate = int(getattr(model.hps.data, "sampling_rate", 44100) or 44100)
            self._model = model
            log.info("MeloTTS Australian voice ready")

    # ---- in the private worker program ----
    def _worker_python(self):
        if self._python is not None:
            return self._python
        from tts import melo_install
        return melo_install.env_python()

    def _start_worker(self):
        python = self._worker_python()
        if python is None:
            raise RuntimeError("the Australian voice is not installed")
        script = Path(__file__).with_name("melo_worker.py")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = self._popen([str(python), str(script)] + self._worker_args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL, text=True, bufsize=1, creationflags=flags, env=_online_env())
        replies = queue.Queue()

        def read():
            try:
                for line in process.stdout:
                    replies.put(line)
            except (OSError, ValueError):
                pass
            replies.put(None)                                   # the worker is gone
        threading.Thread(target=read, name="melo-reader", daemon=True).start()
        self._process, self._replies = process, replies
        first = self._wait(self.LOAD_SECONDS)
        if not first.get("ready"):
            self._stop_worker()
            raise RuntimeError(first.get("error") or "the Australian voice did not start")
        self._rate = int(first.get("rate", 44100) or 44100)
        log.info("MeloTTS Australian voice worker ready")
        if self._watch is None:
            self._watch = threading.Thread(target=self._watch_idle, name="melo-idle", daemon=True)
            self._watch.start()

    def _wait(self, seconds):
        try:
            line = self._replies.get(timeout=seconds)
        except queue.Empty:
            self._stop_worker()
            raise RuntimeError("the Australian voice took too long")
        if line is None:
            self._stop_worker()
            raise RuntimeError("the Australian voice program stopped")
        try:
            return json.loads(line)
        except ValueError:
            raise RuntimeError("the Australian voice sent something unreadable")

    def _stop_worker(self):
        process, self._process = self._process, None
        if process is None:
            return
        try:
            process.stdin.write(json.dumps({"quit": True}) + "\n")
            process.stdin.flush()
        except (OSError, ValueError):
            pass
        try:
            process.terminate()
        except OSError:
            pass

    def close(self):
        with self._lock:
            self._stop_worker()

    def _watch_idle(self):
        while True:
            time.sleep(max(1.0, min(30.0, self.idle_seconds / 4.0)))
            with self._lock:
                if self._process is None:
                    self._watch = None
                    return
                if self._clock() - self._last_used > self.idle_seconds:
                    log.info("MeloTTS Australian voice switched off (not used for a while)")
                    self._stop_worker()
                    self._watch = None
                    return

    def _ask_worker(self, text, speed):
        for attempt in (1, 2):
            with self._lock:
                try:
                    if self._process is None or self._process.poll() is not None:
                        self._start_worker()
                    handle, path = tempfile.mkstemp(suffix=".npy", prefix="melo_")
                    os.close(handle)
                    try:
                        self._process.stdin.write(json.dumps({"text": text, "speed": float(speed or 1.0), "out": path}) + "\n")
                        self._process.stdin.flush()
                        reply = self._wait(self.LINE_SECONDS)
                        if not reply.get("ok"):
                            raise RuntimeError(reply.get("error") or "the Australian voice could not make that line")
                        import numpy as np
                        audio = np.load(path)
                    finally:
                        try:
                            os.unlink(path)
                        except OSError:
                            pass
                    self._last_used = self._clock()
                    return resample(audio, int(reply.get("rate", self._rate) or self._rate))
                except (OSError, ValueError, RuntimeError):
                    self._stop_worker()
                    if attempt == 2:
                        raise

    def __call__(self, text, voice=None, speed=1.0):
        if self._model_factory is not None or (self._python is None and _in_process_possible()):
            self._load()
            audio = self._model.tts_to_file(text, self._speaker, None, speed=float(speed or 1.0))
            yield resample(audio, self._rate)
        else:
            yield self._ask_worker(text, speed)


def _in_process_possible():
    """True when MeloTTS is importable in this program and there is no private install to use instead."""
    try:
        from tts import melo_install
        if melo_install.is_installed():
            return False
        return importlib.util.find_spec("melo") is not None
    except (ImportError, ValueError):
        return False
