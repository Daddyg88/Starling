"""
KokoroTTS: STARLING's local, offline, cloned voice. This REPLACES the Windows "Hazel" voice.

How it works, in plain words:
  * At boot a background thread loads the Kokoro voice engine and your cloned voice
    (custom_covas.pt). The game and the journal reader are not held up.
  * When she needs to say some text, Kokoro turns it into sound (float32 numbers at
    24000 Hz) one sentence at a time. A helper thread makes the sound while the speech
    thread plays the finished pieces, so she starts talking after the FIRST sentence.
  * The sound goes to your default Windows speakers using the 'sounddevice' library.
  * Priorities, cooldowns and "cut her off for a critical warning" are handled by
    the SpeechManager exactly as before - this class only has to speak and stop().
"""

import hashlib
import queue
import threading
import time
from pathlib import Path

from core.logger import get_logger
from tts.base_tts import BaseTTS
from tts import kokoro_voice_setup

log = get_logger("kokoro")

SAMPLE_RATE = 24000
BLOCK_SECONDS = 0.1          # play in 100 ms pieces so stop() reacts quickly
QUEUE_PIECES = 8             # how much finished sound may wait (keeps memory tiny)
PAUSE_MARK = "||"            # in a line: "Four.||Three." means 'one beat between these'
BEAT_SECONDS = 0.95          # each part STARTS about this long after the previous one (just under 1 s)
MIN_GAP_SECONDS = 0.15
MAX_CACHED_CHARS = 200       # longer texts are not cached
SLOW_START_SECONDS = 1.0       # a line that takes longer than this to start is logged as slow
DEFAULT_WAIT_FOR_READY = 45  # seconds a line will wait for the engine to finish loading


def speed_from_rate(rate):
    """settings 'tts.rate' runs -10..10; Kokoro speed is a multiplier (1.0 = normal)."""
    try:
        rate = int(rate)
    except (TypeError, ValueError):
        rate = 0
    return max(0.6, min(1.6, 1.0 + rate * 0.05))


def to_float32_array(piece):
    """Kokoro gives us a Result object, a tuple, a torch tensor or a numpy array. Make it numpy float32."""
    import numpy as np
    audio = getattr(piece, "audio", piece)
    if isinstance(audio, (tuple, list)) and len(audio) == 3:
        audio = audio[2]
    if audio is None:
        return np.zeros(0, dtype=np.float32)
    if hasattr(audio, "detach"):
        audio = audio.detach().cpu().numpy()
    return np.asarray(audio, dtype=np.float32).reshape(-1)


# Free built-in Kokoro voices (American English). "" means Starling's own cloned voice.
BUILT_IN_VOICES = {
    "af_heart": "Heart", "af_bella": "Bella", "af_nicole": "Nicole", "af_sarah": "Sarah",
    "af_sky": "Sky", "af_nova": "Nova", "af_river": "River", "af_jessica": "Jessica",
    "af_kore": "Kore", "af_aoede": "Aoede", "af_alloy": "Alloy",
    "am_adam": "Adam", "am_michael": "Michael", "am_echo": "Echo", "am_eric": "Eric",
    "am_liam": "Liam", "am_onyx": "Onyx", "am_puck": "Puck", "am_fenrir": "Fenrir",
}


class KokoroTTS(BaseTTS):
    name = "kokoro"
    label = "Starling cloned voice (Kokoro, offline)"

    def __init__(self, pack_path, reference_mp3, pipeline_factory=None, torch_load=None,
                 sound_module=None, setup_function=None, wait_for_ready=DEFAULT_WAIT_FOR_READY,
                 cache_dir=None):
        self.pack_path = Path(pack_path)
        self.reference_mp3 = Path(reference_mp3)
        # The four "plug-in points" below exist so tests can use fakes instead of the real libraries.
        self._pipeline_factory = pipeline_factory
        self._torch_load = torch_load
        self._sound_module = sound_module
        self._setup_function = setup_function or kokoro_voice_setup.ensure_custom_voice
        self.wait_for_ready = wait_for_ready
        # Finished sentences are remembered on disk so a repeated line plays INSTANTLY.
        self.cache_dir = Path(cache_dir) if cache_dir else None

        self.pipeline = None
        self.voice_pack = None
        self.last_start_delay = 0.0
        self.ready = threading.Event()
        self.failed_reason = ""
        self.status_message = "not started"
        self._loader = None
        self._stop_flag = threading.Event()
        self._voice_name = ""     # "" = cloned voice; otherwise a built-in voice such as "af_heart"

    def _voice_arg(self):
        """What to hand the engine as `voice=`: the cloned tensor or a built-in voice name."""
        return self.voice_pack if not self._voice_name else self._voice_name

    def _choose_voice(self, name):
        name = (name or "").strip()
        self._voice_name = name if name in BUILT_IN_VOICES else ""

    # ------------------------------------------------------------------
    # Loading (background thread, started at boot)
    # ------------------------------------------------------------------
    def start_loading(self):
        """Begin tuning (if needed) and loading in the background. Safe to call twice."""
        if self._loader is not None:
            return
        self.status_message = "loading"
        self._loader = threading.Thread(target=self._load, name="kokoro-load", daemon=True)
        self._loader.start()

    def wait_until_loaded(self, timeout=None):
        """Block until loading has finished (success or failure). Returns True if she can speak."""
        if self._loader is None:
            self.start_loading()
        self._loader.join(timeout)
        return self.ready.is_set()

    def _load(self):
        try:
            # 1. One-time voice tuning. Skipped instantly if custom_covas.pt exists.
            ok, message = self._setup_function(self.pack_path, self.reference_mp3)
            log.info(message)
            if not ok:
                self._fail(message)
                return

            # 2. Load the voice engine.
            factory = self._pipeline_factory or self._default_pipeline_factory
            self.pipeline = factory()

            # 3. Load the cloned voice tensor.
            loader = self._torch_load or self._default_torch_load
            self.voice_pack = loader(str(self.pack_path))

            # 4. Warm up: the very first sentence is slow, so do a silent one now.
            try:
                for _ in self.pipeline("Ready.", voice=self.voice_pack, speed=1.0):
                    pass
            except Exception:
                log.warning("Warm-up sentence failed (not fatal)", exc_info=True)

            self.status_message = "ready"
            self.ready.set()
            log.info("Kokoro voice ready.")
        except Exception as error:
            log.exception("Kokoro failed to load")
            self._fail("Kokoro failed to load: %s" % error)

    def _fail(self, reason):
        self.failed_reason = reason
        self.status_message = "failed"

    @staticmethod
    def _default_pipeline_factory():
        import warnings
        with warnings.catch_warnings():
            # torch and huggingface print harmless "deprecated" warnings; hide them.
            warnings.simplefilter("ignore")
            from kokoro import KPipeline
            return KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")

    @staticmethod
    def _default_torch_load(path):
        import torch
        return torch.load(path, weights_only=True)

    # ------------------------------------------------------------------
    # BaseTTS interface
    # ------------------------------------------------------------------
    def available(self):
        if self.ready.is_set():
            return True, ""
        if self.failed_reason:
            return False, self.failed_reason
        if self._loader is not None:
            return True, ""        # still loading: lines will wait a short while for it
        return False, "voice not started"

    def list_voices(self):
        return ["custom_covas (cloned)"] + sorted(BUILT_IN_VOICES)

    def speak(self, text, voice, audio_path=None):
        """Say `text`. Returns True if it was spoken (or deliberately cut off)."""
        if not text or not text.replace(PAUSE_MARK, "").strip():
            return False
        try:
            if not self._wait_until_ready():
                return False
            sound = self._get_sound_module()
            if sound is None:
                return False
            self._choose_voice(getattr(voice, "voice", ""))
            done = self._synthesise_and_play(text, voice, sound)
            if not done and self._voice_name and not self._stop_flag.is_set():
                # A built-in voice could not be made (for example no internet for its first download).
                log.warning("Voice %s failed; using the cloned voice instead", self._voice_name)
                self._voice_name = ""
                done = self._synthesise_and_play(text, voice, sound)
            return done
        except Exception:
            log.exception("Kokoro speech problem")
            return False
        finally:
            self._stop_flag.clear()

    def stop(self):
        self._stop_flag.set()

    # ------------------------------------------------------------------
    # The sound cache (so a line only has to be made once)
    # ------------------------------------------------------------------
    def _cache_file(self, text, speed):
        if self.cache_dir is None or len(text) > MAX_CACHED_CHARS:
            return None
        try:
            stat = self.pack_path.stat()
            stamp = "%d-%d" % (stat.st_mtime_ns, stat.st_size)   # a re-tuned voice makes a new cache
        except OSError:
            stamp = "nopack"
        key = hashlib.sha1(("%s|%.2f|%s|%s" % (text, speed, stamp, self._voice_name)).encode("utf-8")).hexdigest()[:24]
        return self.cache_dir / (key + ".npy")

    def _cache_load(self, text, speed):
        import numpy as np
        path = self._cache_file(text, speed)
        if path is None or not path.is_file():
            return None
        try:
            return np.load(path).astype(np.float32) / 32767.0
        except (OSError, ValueError):
            return None

    def _cache_save(self, text, speed, audio):
        import numpy as np
        path = self._cache_file(text, speed)
        if path is None or audio.size == 0:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(path.name + ".tmp")
            with open(temp, "wb") as handle:
                np.save(handle, (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16))
            temp.replace(path)
        except OSError:
            log.warning("Could not save to the voice cache", exc_info=True)

    def is_cached(self, text, speed=1.0):
        """True if this exact sentence is already made (so it will play instantly)."""
        path = self._cache_file(text, speed)
        return path is not None and path.is_file()

    def render(self, text, speed=1.0):
        """Make the sound for `text` WITHOUT playing it (and cache it). Returns True on success."""
        parts = [part.strip() for part in text.split(PAUSE_MARK) if part.strip()]
        if len(parts) != 1:
            return bool(parts) and all([self.render(part, speed) for part in parts])
        text = parts[0]
        if not self._wait_until_ready():
            return False
        if self._cache_load(text, speed) is not None:
            return True
        import numpy as np
        pieces = [to_float32_array(p) for p in self.pipeline(text, voice=self._voice_arg(), speed=speed)]
        pieces = [p for p in pieces if p.size]
        if not pieces:
            return False
        self._cache_save(text, speed, np.concatenate(pieces))
        return True

    def _note_start_delay(self, seconds, first_part):
        """How long she took to START talking. Slow starts almost always mean the sentence was not in the voice cache."""
        self.last_start_delay = seconds
        if seconds >= SLOW_START_SECONDS:
            log.info("Slow start: %.1f s before she began %r (%s). Say 'prepare her voice' or run run_build_voice_cache.bat.",
                     seconds, first_part[:40], "made on the spot")
        else:
            log.debug("She started after %.2f s", seconds)

    # ------------------------------------------------------------------
    # Inside speak()
    # ------------------------------------------------------------------
    def _wait_until_ready(self):
        deadline = time.monotonic() + self.wait_for_ready
        while not self.ready.is_set():
            if self.failed_reason or self._stop_flag.is_set() or self._loader is None:
                return False
            if time.monotonic() > deadline:
                log.warning("The voice engine was not ready in time; dropping a line.")
                return False
            self.ready.wait(0.1)
        return True

    def _get_sound_module(self):
        if self._sound_module is not None:
            return self._sound_module
        try:
            import sounddevice
        except Exception as error:      # missing package or no audio system
            log.error("sounddevice is not usable (%s)", error)
            return None
        self._sound_module = sounddevice
        return sounddevice

    def _synthesise_and_play(self, text, voice, sound):
        import numpy as np
        gain = max(0.0, min(1.0, voice.volume / 100.0))
        speed = speed_from_rate(voice.rate)
        pieces = queue.Queue(maxsize=QUEUE_PIECES)
        end = object()
        problem = []

        parts = [part.strip() for part in text.split(PAUSE_MARK) if part.strip()]
        started_at = time.monotonic()

        def make_part(part):
            """Make (or load from the cache) one part. Returns how many samples were queued."""
            cached = self._cache_load(part, speed)
            if cached is not None:
                self._put(pieces, cached * gain)
                return cached.size
            made = []
            for piece in self.pipeline(part, voice=self._voice_arg(), speed=speed):
                if self._stop_flag.is_set():
                    return 0
                audio = to_float32_array(piece)
                if audio.size:
                    made.append(audio)
                    self._put(pieces, audio * gain)
            if made and not self._stop_flag.is_set():
                self._cache_save(part, speed, np.concatenate(made))
            return sum(a.size for a in made)

        def make_sound():
            """Helper thread: makes one sentence at a time and queues it (with beats between parts)."""
            try:
                for number, part in enumerate(parts):
                    if self._stop_flag.is_set():
                        return
                    length = make_part(part)
                    if number < len(parts) - 1:
                        gap = max(MIN_GAP_SECONDS, BEAT_SECONDS - length / float(SAMPLE_RATE))
                        self._put(pieces, np.zeros(int(gap * SAMPLE_RATE), dtype=np.float32))
            except Exception as error:
                problem.append(error)
                log.exception("Kokoro could not make the sound")
            finally:
                self._put(pieces, end, force=True)

        maker = threading.Thread(target=make_sound, name="kokoro-synth", daemon=True)
        maker.start()

        block = int(SAMPLE_RATE * BLOCK_SECONDS)
        played_any = False
        stream = sound.OutputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32")
        stream.start()
        try:
            while not self._stop_flag.is_set():
                try:
                    piece = pieces.get(timeout=0.1)
                except queue.Empty:
                    continue
                if piece is end:
                    break
                for start in range(0, piece.size, block):
                    if self._stop_flag.is_set():
                        break
                    chunk = np.ascontiguousarray(piece[start:start + block], dtype=np.float32)
                    stream.write(chunk.reshape(-1, 1))
                    if not played_any:
                        self._note_start_delay(time.monotonic() - started_at, parts[0])
                    played_any = True
        finally:
            try:
                stream.stop()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
            # Let the helper thread finish (it checks the stop flag between sentences).
            maker.join(timeout=2)
        if self._stop_flag.is_set():
            return True          # we were cut off on purpose (e.g. by a critical warning)
        return played_any and not problem

    def _put(self, q, item, force=False):
        """Put into the bounded queue, but give up quickly if we were told to stop."""
        while True:
            try:
                q.put(item, timeout=0.1)
                return
            except queue.Full:
                if self._stop_flag.is_set():
                    if force:
                        try:
                            q.get_nowait()
                        except queue.Empty:
                            pass
                        continue
                    return
