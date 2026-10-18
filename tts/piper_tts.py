"""Piper (offline neural voice). A slot is reserved for it, but it is not built yet."""

from tts.base_tts import BaseTTS


class PiperTTS(BaseTTS):
    name = "piper"
    label = "Piper (offline neural voice)"

    def available(self):
        return False, "not added yet (planned for a later update)"

    def speak(self, text, voice, audio_path=None):
        return False
