"""
Faster-Whisper: offline speech recognition that runs on your CPU.

Why this one: it is accurate, free, needs no internet after the first download, and the
small English model ("tiny.en", about 75 MB) is light enough to run beside the game.
The model is downloaded the first time and then cached by Windows.
"""

import threading

from core.logger import get_logger
from stt.base_stt import BaseSTT

log = get_logger("faster_whisper")

# Gentle hints that help Whisper spell the words she will hear most.
HINT = "Starling. Commander. Elite Dangerous. galaxy map, system map, supercruise, hyperspace, fuel scoop."


class FasterWhisperSTT(BaseSTT):
    name = "faster_whisper"
    label = "Faster-Whisper (offline)"

    def __init__(self, model_size="tiny.en", cpu_threads=2, model_factory=None):
        self.model_size = model_size or "tiny.en"
        self.cpu_threads = cpu_threads        # kept small so the game keeps its speed
        self._model_factory = model_factory   # tests pass a fake here
        self._model = None
        self._lock = threading.Lock()

    def available(self):
        if self._model_factory is not None:
            return True, ""
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False, "faster-whisper is not installed (run setup.bat again)"
        return True, ""

    def load(self):
        with self._lock:
            if self._model is not None:
                return
            if self._model_factory is not None:
                self._model = self._model_factory()
                return
            from faster_whisper import WhisperModel
            log.info("Loading the %s listening model (first time downloads it)...", self.model_size)
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8",
                                       cpu_threads=self.cpu_threads)
            log.info("Listening model ready.")

    def transcribe(self, audio):
        if self._model is None:
            self.load()
        segments, _info = self._model.transcribe(
            audio, language="en", beam_size=1, vad_filter=False,
            condition_on_previous_text=False, initial_prompt=HINT,
            temperature=0.0, no_speech_threshold=0.6,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return text
