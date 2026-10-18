"""Finding microphones and reading from the one you chose."""

import queue

from core.logger import get_logger
from stt.vad import RATE

log = get_logger("microphone")


def _sounddevice():
    import sounddevice
    return sounddevice


def list_microphones(sound=None):
    """Returns [(number, name), ...] for every device that can record."""
    try:
        sound = sound or _sounddevice()
        devices = sound.query_devices()
    except Exception as error:
        log.warning("Could not list microphones: %s", error)
        return []
    found = []
    for number, device in enumerate(devices):
        if device.get("max_input_channels", 0) > 0:
            found.append((number, device.get("name", "device %d" % number)))
    return found


def find_microphone(wanted, sound=None):
    """Device number for the name (or part of a name) in settings.json. None = Windows default."""
    wanted = (wanted or "").strip().lower()
    if not wanted:
        return None
    if wanted.isdigit():
        return int(wanted)
    for number, name in list_microphones(sound):
        if wanted in name.lower():
            return number
    log.warning("Microphone %r was not found; using the Windows default", wanted)
    return None


class MicrophoneStream:
    """Hands out 30 ms blocks of sound, 16000 times a second, as a stream of float32 numbers."""

    def __init__(self, device=None, frame_samples=480, sound=None):
        self.device = device
        self.frame_samples = frame_samples
        self._sound = sound
        self._stream = None
        self.frames = queue.Queue(maxsize=200)   # about 6 seconds; old sound is dropped, never piled up
        self.overflows = 0

    def start(self):
        sound = self._sound or _sounddevice()
        self._stream = sound.InputStream(samplerate=RATE, channels=1, dtype="float32",
                                         blocksize=self.frame_samples, device=self.device,
                                         callback=self._callback)
        self._stream.start()

    def _callback(self, indata, frames, time_info, status):
        try:
            self.frames.put_nowait(indata[:, 0].copy())
        except queue.Full:
            self.overflows += 1

    def read(self, timeout=0.5):
        try:
            return self.frames.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
