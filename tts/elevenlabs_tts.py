"""ElevenLabs (online). A slot is reserved for it, but it is not built yet."""

from tts.base_tts import BaseTTS


class ElevenLabsTTS(BaseTTS):
    name = "elevenlabs"
    label = "ElevenLabs (online)"

    def available(self):
        return False, "not added yet (planned for a later update)"

    def speak(self, text, voice, audio_path=None):
        return False
