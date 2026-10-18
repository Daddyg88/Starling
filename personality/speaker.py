"""
The EventSpeaker: listens to game events and decides what STARLING says.

For each event she:
  1. checks she hasn't just spoken about it (cooldowns in config/speech.json),
  2. finds the right dialogue key and picks a line that suits her mood,
  3. hands it to the SpeechManager.

SAFETY RULE: if a critical event has no dialogue line at all, she speaks the
event's own summary instead, so a warning is never silent.
"""

import json
import time

from core.logger import get_logger
from personality.mood_engine import effective_mood
from core import paths
from core.identity import personalise
from personality import line_keys

log = get_logger("speaker")

_SKIP_PREFIXES = ("app.", "journal.", "speech.", "voice.", "personality.", "ask.")

DEFAULT_RULES = {
    "default_cooldown_seconds": 2.5,
    "cooldown_seconds": {},
    "max_age_seconds": {"critical": 30, "normal": 8, "low": 4},
}


def load_rules(path=None):
    """Read config/speech.json. Falls back to safe defaults if it is missing or damaged."""
    rules = json.loads(json.dumps(DEFAULT_RULES))
    path = path or (paths.CONFIG_DIR / "speech.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            saved = json.load(handle)
        for key in rules:
            if key in saved and isinstance(saved[key], type(rules[key])):
                rules[key] = saved[key]
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as error:
        log.error("Could not read speech.json (%s); using defaults", error)
    return rules


class EventSpeaker:
    def __init__(self, bus, speech, dialogue, settings, rules=None, clock=time.monotonic, flavour=None, echo=None):
        self.bus = bus
        self.speech = speech
        self.dialogue = dialogue
        self.settings = settings
        self.rules = rules or DEFAULT_RULES
        self.clock = clock
        self._last_spoken = {}
        self.echo = echo            # optional: control/echo.py, skips events caused by her own voice commands
        self.flavour = flavour      # optional: adds pet names and remarks (personality style only)

    def attach(self):
        self.bus.subscribe("*", self.on_event)

    def _cooldown_for(self, name):
        return float(self.rules["cooldown_seconds"].get(name, self.rules["default_cooldown_seconds"]))

    def on_event(self, event):
        if event.name.startswith(_SKIP_PREFIXES):
            return
        if not self.settings.get("speech.enabled", True):
            return
        if self.echo is not None and self.echo.consume(event):
            return          # she has just told you she did this herself

        if event.name == "LoadGame" and self.settings.get("personality.login_greeting", True):
            return          # the login greeting (personality/greeter.py) says hello instead
        now = self.clock()
        last = self._last_spoken.get(event.name)
        if last is not None and now - last < self._cooldown_for(event.name):
            return

        mood = effective_mood(self.settings)
        if self.settings.get("personality.style", "personality") == "info":
            mood = ""            # info style: plain, neutral lines only
        allow_mature = bool(self.settings.get("speech.allow_mature", False))
        prefer_recorded = bool(self.settings.get("speech.use_recordings", True))

        line = None
        for key in line_keys.keys_for(event):
            line = self.dialogue.pick(key, mood, allow_mature, prefer_recorded)
            if line is not None:
                break

        if line is None:
            if event.priority != "critical":
                return  # nothing to say about this one
            summary = event.data.get("summary")
            if not summary:
                return
            self._last_spoken[event.name] = now
            self.speech.say(text=summary, priority="critical", event_name=event.name)
            return

        priority = event.priority
        if event.name == "Scan" and priority == "low":
            priority = "normal"     # only interesting bodies get this far, so let them be heard
        text = personalise(self._fill_in(line.text, event), self.settings)
        if self.flavour is not None and not line.audio:
            text = self.flavour.apply(text, priority)
        after = personalise(self._fill_in(line.after_text, event, use_summary=False), self.settings) if line.after_text else None
        self._last_spoken[event.name] = now
        self.speech.say(
            text=text,
            audio_path=self.dialogue.audio_path(line) if prefer_recorded else None,
            speak_text_after=line.then_speak,
            after_text=after or None,
            priority=priority,
            event_name=event.name,
        )

    @staticmethod
    def _fill_in(text, event, use_summary=True):
        """Put event details into a line, e.g. {fuel_percent}. Falls back to the summary."""
        if "{" not in text:
            return text
        try:
            return text.format(**event.data)
        except (KeyError, IndexError, ValueError):
            return (event.data.get("summary") or text) if use_summary else None
