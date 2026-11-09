"""AUSTRALIAN VOICE (MeloTTS): an optional extra voice for her, picked in Settings > Voice as "Australian (MeloTTS)".

Why it is an extra voice and not a separate engine: it plugs into the same voice code as her Kokoro voices (tts/kokoro_tts.py), so the
saved-line cache, the voice warm-up, speed, volume and stopping all work exactly as before, and a line made once plays instantly next time.

MeloTTS is a free (MIT licence) offline voice that runs on the processor. Its English model has an Australian accent ("EN-AU").
It is NOT installed with her. To try it (running from source):
    pip install git+https://github.com/myshell-ai/MeloTTS.git
    python -m unidic download
The first use downloads the model (about 200 MB) and some language data, so it needs the internet once.
If MeloTTS is missing or fails, she quietly uses her normal voice and says why in the log.
"""
import importlib.util
import threading

from core.logger import get_logger

log = get_logger("melo")

VOICE_NAME = "melo_en_au"            # the name used in settings (tts.voice) and in the voice list
ACCENT = "EN-AU"                     # the speaker inside the MeloTTS English model
OUTPUT_RATE = 24000                  # the rate her sound code plays at (MeloTTS makes 44100)


def is_installed():
    """True when the MeloTTS package can be found (it is not part of the normal install)."""
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


class MeloEngine:
    """Looks like Kokoro's engine: engine(text, voice=..., speed=...) gives pieces of sound at 24000 Hz. Loaded the first time it is used."""

    def __init__(self, model_factory=None):
        self._model_factory = model_factory
        self._model = None
        self._speaker = None
        self._rate = 44100
        self._lock = threading.Lock()

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

    def __call__(self, text, voice=None, speed=1.0):
        self._load()
        audio = self._model.tts_to_file(text, self._speaker, None, speed=float(speed or 1.0))
        yield resample(audio, self._rate)
