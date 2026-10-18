"""Plays your recorded mp3 lines (the Starling voice)."""

from pathlib import Path

from core.logger import get_logger
from tts.base_tts import BaseTTS
from tts.mci_player import MciPlayer, PlaybackError

log = get_logger("recorded")


class PrerecordedTTS(BaseTTS):
    name = "recorded"
    label = "Recorded voice lines (mp3)"

    def __init__(self, player=None):
        self.player = player or MciPlayer()

    def available(self):
        if self.player.available():
            return True, ""
        return False, "playing mp3 files needs Windows"

    def speak(self, text, voice, audio_path=None):
        if not self.player.available():
            return False
        if not audio_path or not Path(audio_path).is_file():
            return False
        try:
            self.player.play(str(audio_path), voice.volume)
            return True
        except PlaybackError as error:
            log.warning("%s", error)
            return False
        except Exception:
            log.exception("Unexpected problem playing %s", audio_path)
            return False

    def stop(self):
        self.player.stop()
