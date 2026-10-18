"""
The template every speech-to-text provider is built from.

A "provider" is one way of turning what you say into text:
Faster-Whisper (offline, recommended), Whisper, Windows speech recognition...
Adding a new one means writing one small file like this one.
"""


class BaseSTT:
    name = ""      # short id used in settings.json, e.g. "faster_whisper"
    label = ""     # friendly name shown to you

    def available(self):
        """Returns (True, "") if it can work, or (False, "the reason")."""
        return False, "not implemented"

    def load(self):
        """Get ready (load the model). Called once on a background thread."""

    def transcribe(self, audio):
        """
        audio: a numpy float32 array, mono, 16000 samples per second, values -1..1.
        Returns the text that was said ("" if nothing was understood).
        """
        raise NotImplementedError
