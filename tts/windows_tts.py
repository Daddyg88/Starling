"""
The Windows built-in voice (the same one Narrator uses).

STARLING asks PowerShell to speak for her. That means nothing extra to install,
and while she is not speaking it uses no memory at all.
"""

import os
import shutil
import subprocess
import sys
import threading
from xml.sax.saxutils import escape

from core.logger import get_logger
from tts.base_tts import BaseTTS

log = get_logger("windows_tts")

# The PowerShell script never changes. Everything else is passed in through
# environment variables, so odd characters in the text can't break anything.
_SPEAK_SCRIPT = (
    "Add-Type -AssemblyName System.Speech; "
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "$s.Volume = [int]$env:STARLING_VOLUME; "
    "$s.Rate = [int]$env:STARLING_RATE; "
    "if ($env:STARLING_VOICE) { try { $s.SelectVoice($env:STARLING_VOICE) } catch { } }; "
    "if ($env:STARLING_SSML -eq '1') { $s.SpeakSsml($env:STARLING_SAY) } else { $s.Speak($env:STARLING_SAY) }"
)

_LIST_SCRIPT = (
    "Add-Type -AssemblyName System.Speech; "
    "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() "
    "| ForEach-Object { $_.VoiceInfo.Name }"
)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _pitch_word(pitch):
    if pitch >= 7:
        return "x-high"
    if pitch >= 3:
        return "high"
    if pitch <= -7:
        return "x-low"
    if pitch <= -3:
        return "low"
    return None


def build_environment(text, voice, base_env=None):
    """The environment variables handed to PowerShell for one sentence."""
    env = dict(os.environ if base_env is None else base_env)
    say = text
    ssml = "0"
    word = _pitch_word(voice.pitch)
    if word:
        say = (
            '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="en-US">'
            '<prosody pitch="%s">%s</prosody></speak>' % (word, escape(text))
        )
        ssml = "1"
    env.update({
        "STARLING_SAY": say,
        "STARLING_SSML": ssml,
        "STARLING_VOICE": voice.voice or "",
        "STARLING_VOLUME": str(voice.volume),
        "STARLING_RATE": str(voice.rate),
    })
    return env


class WindowsTTS(BaseTTS):
    name = "windows"
    label = "Windows voice"

    def __init__(self):
        self._proc = None
        self._lock = threading.Lock()
        self._stopped = False
        self._voices = None

    def _powershell(self):
        return shutil.which("powershell")

    def available(self):
        if sys.platform != "win32":
            return False, "the Windows voice needs Windows"
        if not self._powershell():
            return False, "PowerShell was not found"
        return True, ""

    def list_voices(self):
        if self._voices is None:
            self._voices = []
            if self.available()[0]:
                try:
                    result = subprocess.run(
                        [self._powershell(), "-NoProfile", "-NonInteractive", "-Command", _LIST_SCRIPT],
                        capture_output=True, text=True, timeout=20, creationflags=_NO_WINDOW,
                    )
                    self._voices = [line.strip() for line in result.stdout.splitlines() if line.strip()]
                except (OSError, subprocess.SubprocessError):
                    log.exception("Could not list Windows voices")
        return list(self._voices)

    def speak(self, text, voice, audio_path=None):
        if not text or not self.available()[0]:
            return False
        env = build_environment(text, voice)
        command = [self._powershell(), "-NoProfile", "-NonInteractive",
                   "-ExecutionPolicy", "Bypass", "-Command", _SPEAK_SCRIPT]
        try:
            with self._lock:
                self._stopped = False
                self._proc = subprocess.Popen(
                    command, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE, creationflags=_NO_WINDOW,
                )
                proc = self._proc
            _out, err = proc.communicate(timeout=90)
            if self._stopped:
                return True
            if proc.returncode != 0:
                log.warning("Windows voice failed: %s", (err or b"").decode("utf-8", "replace").strip()[:300])
                return False
            return True
        except (OSError, subprocess.SubprocessError):
            log.exception("Windows voice problem")
            return False
        finally:
            with self._lock:
                self._proc = None

    def stop(self):
        with self._lock:
            self._stopped = True
            proc = self._proc
        if proc is not None:
            try:
                proc.terminate()
            except OSError:
                pass
