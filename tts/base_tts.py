"""
The template every voice provider is built from.

A "provider" is one way of making STARLING talk: the Windows voice, your
recorded mp3 files, Piper, ElevenLabs, Azure... Every provider answers the
same few questions, so the rest of STARLING never cares which one is in use.
"""

from dataclasses import dataclass


@dataclass
class VoiceSettings:
    voice: str = ""      # name of the voice ("" = the default one)
    volume: int = 100    # 0 to 100
    rate: int = 0        # -10 (slow) to 10 (fast)
    pitch: int = 0       # -10 (low) to 10 (high)

    @classmethod
    def from_settings(cls, settings):
        def clamp(value, low, high):
            try:
                return max(low, min(high, int(value)))
            except (TypeError, ValueError):
                return 0
        return cls(
            voice=str(settings.get("tts.voice", "") or ""),
            volume=clamp(settings.get("tts.volume", 100), 0, 100),
            rate=clamp(settings.get("tts.rate", 0), -10, 10),
            pitch=clamp(settings.get("tts.pitch", 0), -10, 10),
        )


class BaseTTS:
    name = ""     # short id used in settings.json, e.g. "windows"
    label = ""    # friendly name shown to people

    def available(self):
        """Returns (True, "") if usable, or (False, "reason it is not")."""
        return False, "not implemented"

    def list_voices(self):
        """Names of the voices this provider offers."""
        return []

    def speak(self, text, voice, audio_path=None):
        """
        Say it, and don't return until it has finished (or been stopped).
        Returns True if sound was produced, False if it failed.
        """
        raise NotImplementedError

    def stop(self):
        """Cut off whatever is being said right now. Safe to call from any thread."""
