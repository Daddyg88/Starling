"""Whisper (OpenAI). A slot is reserved for it, but it is not built yet."""

from stt.base_stt import BaseSTT


class WhisperSTT(BaseSTT):
    name = "whisper"
    label = "Whisper (OpenAI)"

    def available(self):
        return False, "not added yet (Faster-Whisper is used instead)"

    def transcribe(self, audio):
        return ""
