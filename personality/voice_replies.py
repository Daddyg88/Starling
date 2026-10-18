"""
What STARLING does when she hears you.

  * you say her name alone ("Starling?")        -> she answers ("Yes, Commander?")
  * you say her name and a request           -> the CommandRunner (control/runner.py) carries it out.
    Only if voice commands are switched off does she say she cannot do that.
  * you talk without saying her name         -> she stays quiet (unless stt.require_wake is false)
"""

from core.logger import get_logger
from core.identity import personalise
from personality.mood_engine import effective_mood

log = get_logger("voice_replies")


class VoiceReplies:
    def __init__(self, bus, speech, dialogue, settings, commands_active=False):
        self.commands_active = commands_active    # True when the CommandRunner answers requests instead
        self.bus = bus
        self.speech = speech
        self.dialogue = dialogue
        self.settings = settings

    def attach(self):
        self.bus.subscribe("voice.heard", self.on_heard)

    def detach(self):
        self.bus.unsubscribe("voice.heard", self.on_heard)

    def on_heard(self, event):
        if not self.settings.get("stt.reply", True) or not self.settings.get("speech.enabled", True):
            return
        data = event.data
        wake = data.get("wake")
        if self.commands_active and self.settings.get("commands.enabled", True):
            # The CommandRunner answers requests. We only answer the name on its own.
            if not wake or data.get("command"):
                return
        elif not wake and self.settings.get("stt.require_wake", True):
            return
        key = "CommandNotReady" if data.get("command") else "WakeHeard"
        mood = effective_mood(self.settings)
        allow_mature = bool(self.settings.get("speech.allow_mature", False))
        line = self.dialogue.pick(key, mood, allow_mature, False)
        if line is None:
            return
        self.speech.say(text=personalise(line.text, self.settings), priority="normal", event_name="voice.heard")
