"""Windows speech recognition. A slot is reserved for it, but it is not built yet."""

from stt.base_stt import BaseSTT


class WindowsSTT(BaseSTT):
    name = "windows"
    label = "Windows speech recognition"

    def available(self):
        return False, "not added yet (Faster-Whisper is used instead)"

    def transcribe(self, audio):
        return ""
