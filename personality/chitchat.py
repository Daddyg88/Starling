"""
CHIT-CHAT - when it has been too quiet she says something small and silly.

She only chats when ALL of these are true:
  * you are actually in the game (Status.json is alive and you are not in a menu)
  * nothing has been spoken for a while (the quiet time)
  * she has not chatted for a while (the gap, plus some random wobble so it isn't a clock)
  * nothing alarming happened in the last minute (under attack, interdicted, low fuel, overheating...)
  * the speaker is free (chatter is "low" priority, so a real warning always wins and chatter is simply dropped)
In combat mode the chat is about the fight, in analysis mode about exploring, docked about the station, and so on.
Her words are in voicepacks/default/chitchat.json (keys ChitChat_General, _Combat, _Analysis, _Docked, _Supercruise).
"""
import random
import threading
import time

from core.identity import personalise
from core.logger import get_logger
from personality.mood_engine import effective_mood

log = get_logger("chitchat")

# frequency -> (seconds of silence needed, minimum seconds between two chats)
FREQUENCY = {"rarely": (600.0, 1500.0), "normal": (300.0, 720.0), "often": (150.0, 360.0)}
ALARMS = ("UnderAttack", "Interdicted", "InterdictionInProgress", "LowFuel", "Overheating", "HeatWarning", "HeatDamage",
          "HullDamage", "InDanger", "LowHealth", "LowOxygen", "Died", "CockpitBreached", "ShieldState")
ALARM_QUIET_SECONDS = 75.0
CHECK_EVERY_SECONDS = 15.0


class ChitChat:
    def __init__(self, bus, speech, dialogue, settings, state_provider=None, active_provider=None,
                 clock=time.monotonic, rng=None):
        self.bus = bus
        self.speech = speech
        self.dialogue = dialogue
        self.settings = settings
        self.state_provider = state_provider or (lambda: None)
        self.active_provider = active_provider or (lambda: True)
        self.clock = clock
        self.rng = rng or random.Random()
        now = clock()
        self.last_spoke = now            # starting up counts as "just spoke"
        self.last_chat = now
        self.last_alarm = None
        self.mode = "general"            # "combat" or "analysis" (from the cockpit's mode switch), else general
        self._wobble = 1.0
        self._stop = threading.Event()
        self._thread = None

    # ---- listening ----
    def attach(self):
        self.bus.subscribe("*", self.on_event)

    def on_event(self, event):
        name = event.name
        now = self.clock()
        if name in ("speech.started", "speech.finished"):
            self.last_spoke = now
        elif name == "CombatModeOn":
            self.mode = "combat"
        elif name == "AnalysisModeOn":
            self.mode = "analysis"
        elif name in ALARMS:
            self.last_alarm = now

    # ---- deciding ----
    def _timing(self):
        quiet, gap = FREQUENCY.get(str(self.settings.get("chitchat.frequency", "normal")), FREQUENCY["normal"])
        if self.mode == "combat":
            quiet = quiet / 2.0                     # a fight is livelier; she may chip in a little sooner
        return quiet, gap

    def enabled(self):
        return (bool(self.settings.get("chitchat.enabled", True)) and bool(self.settings.get("speech.enabled", True))
                and self.settings.get("personality.style", "personality") == "personality")

    def due(self, now=None):
        now = self.clock() if now is None else now
        if not self.enabled() or not self.active_provider():
            return False
        quiet, gap = self._timing()
        if now - self.last_spoke < quiet:
            return False
        if now - self.last_chat < gap * self._wobble:
            return False
        if self.last_alarm is not None and now - self.last_alarm < ALARM_QUIET_SECONDS:
            return False
        return True

    def pool_key(self):
        state = self.state_provider()
        if self.mode == "combat":
            return "ChitChat_Combat"
        if self.mode == "analysis":
            if getattr(state, "docked", False):
                return "ChitChat_Docked"
            return "ChitChat_Analysis"
        if getattr(state, "docked", False):
            return "ChitChat_Docked"
        if getattr(state, "in_supercruise", False):
            return "ChitChat_Supercruise"
        return "ChitChat_General"

    def tick(self, now=None):
        """Called every few seconds. Says one small thing if it is time. Returns the text or None."""
        now = self.clock() if now is None else now
        try:
            if not self.due(now):
                return None
            mood = effective_mood(self.settings) or ""
            allow = bool(self.settings.get("speech.allow_mature", False))
            key = self.pool_key()
            line = self.dialogue.pick(key, mood, allow, False)
            if line is None and key != "ChitChat_General":
                line = self.dialogue.pick("ChitChat_General", mood, allow, False)
            if line is None:
                return None
            text = personalise(line.text, self.settings)
            if not self.speech.say(text=text, priority="low", event_name="chitchat"):
                return None                          # she was busy: try again at the next check
            self.last_chat = self.last_spoke = now
            self._wobble = self.rng.uniform(1.0, 1.8)    # so the gap is never the same twice
            return text
        except Exception:
            log.exception("Chit-chat problem")
            return None

    # ---- the little timer ----
    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="chitchat", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.wait(CHECK_EVERY_SECONDS):
            self.tick()
