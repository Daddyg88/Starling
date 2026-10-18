"""
CHIT-CHAT - when it has been too quiet she says something small and silly.

She only chats when ALL of these are true:
  * you are actually in the game (Status.json is alive and you are not in a menu)
  * nothing has been spoken for a while (the quiet time)
  * she has not chatted for a while (the gap, plus some random wobble so it isn't a clock)
  * nothing alarming happened in the last minute (under attack, interdicted, low fuel, overheating...)
  * the speaker is free (chatter is "low" priority, so a real warning always wins and chatter is simply dropped)
In combat mode the chat is about the fight, in analysis mode about exploring, docked about the station, and so on.
Her words are in voicepacks/default/chitchat.json (keys ChitChat_General, _Combat, _Analysis, _Docked, _Supercruise, _Flying).
Lines in ChitChat_Flying can mention real things: {ship}, {system}, {station}, {jumps}, {distance}, {minutes}. A line is only used
when she knows every value in it. She may also bring up a memory (memory/recall.py).
"""
import random
import threading
import time

from core.identity import personalise
from core.logger import get_logger
from personality.mood_engine import effective_mood

log = get_logger("chitchat")

# frequency -> (seconds of silence needed, minimum seconds between two chats)
FREQUENCY = {"rarely": (600.0, 1500.0), "normal": (150.0, 360.0), "often": (90.0, 210.0), "chatty": (50.0, 120.0)}
ALARMS = ("UnderAttack", "Interdicted", "InterdictionInProgress", "LowFuel", "Overheating", "HeatWarning", "HeatDamage",
          "HullDamage", "InDanger", "LowHealth", "LowOxygen", "Died", "CockpitBreached", "ShieldState")
ALARM_QUIET_SECONDS = 75.0
CHECK_EVERY_SECONDS = 15.0


class ChitChat:
    def __init__(self, bus, speech, dialogue, settings, state_provider=None, active_provider=None,
                 clock=time.monotonic, rng=None, memory=None):
        self.bus = bus
        self.speech = speech
        self.dialogue = dialogue
        self.settings = settings
        self.state_provider = state_provider or (lambda: None)
        self.active_provider = active_provider or (lambda: True)
        self.clock = clock
        self.rng = rng or random.Random()
        self.memory = memory             # memory/recall.py (optional): she sometimes brings up something she remembers
        self.started = clock()
        self.jumps = 0
        self.distance = 0.0
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
        elif name == "FSDJump":
            self.jumps += 1
            dist = (event.data or {}).get("JumpDist")
            if isinstance(dist, (int, float)) and dist > 0:
                self.distance += float(dist)
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

    def candidate_keys(self):
        """Which pools she may use right now, most fitting first. She picks one at random."""
        state = self.state_provider()
        docked = bool(getattr(state, "docked", False))
        if self.mode == "combat":
            return ["ChitChat_Combat"]
        if docked:
            return ["ChitChat_Docked", "ChitChat_Flying"]
        if self.mode == "analysis":
            return ["ChitChat_Analysis", "ChitChat_Flying"]
        if getattr(state, "in_supercruise", False):
            return ["ChitChat_Supercruise", "ChitChat_Flying", "ChitChat_General"]
        return ["ChitChat_General", "ChitChat_Flying"]

    def pool_key(self):
        return self.candidate_keys()[0]

    def context(self, now=None):
        """The real things she can mention. Missing ones are left out so a line that needs them is never used."""
        now = self.clock() if now is None else now
        state = self.state_provider()
        values = {}
        ship = getattr(state, "ship", None)
        if ship:
            ship = str(ship).replace("_", " ")
            values["ship"] = ship.title() if ship.islower() else ship
        if getattr(state, "system", None):
            values["system"] = state.system
        if getattr(state, "docked", False) and getattr(state, "station", None):
            values["station"] = state.station
        if self.jumps >= 3:
            values["jumps"] = self.jumps
        if self.distance >= 50:
            values["distance"] = int(round(self.distance))
        minutes = int((now - self.started) / 60)
        if minutes >= 20:
            values["minutes"] = minutes
        return values

    def _pick_text(self, now, mood, allow):
        values = self.context(now)
        keys = list(self.candidate_keys())
        self.rng.shuffle(keys)
        keys.append("ChitChat_General")
        for key in keys:
            for _ in range(6):
                line = self.dialogue.pick(key, mood, allow, False)
                if line is None:
                    break
                try:
                    return line.text.format(**values)       # needs every value it mentions
                except (KeyError, IndexError, ValueError):
                    continue
        return None

    def _memory_text(self):
        if self.memory is None or self.rng.random() > 0.2:
            return None
        try:
            return self.memory.login_line()
        except Exception:
            log.exception("Chit-chat could not recall a memory")
            return None

    def tick(self, now=None):
        """Called every few seconds. Says one small thing if it is time. Returns the text or None."""
        now = self.clock() if now is None else now
        try:
            if not self.due(now):
                return None
            mood = effective_mood(self.settings) or ""
            allow = bool(self.settings.get("speech.allow_mature", False))
            text = self._memory_text() if self.mode != "combat" else None
            if not text:
                text = self._pick_text(now, mood, allow)
            if not text:
                return None
            text = personalise(text, self.settings)
            if not self.speech.say(text=text, priority="low", event_name="chitchat"):
                return None                          # she was busy: try again at the next check
            self.last_chat = self.last_spoke = now
            self._wobble = self.rng.uniform(1.0, 1.8)    # so the gap is never the same twice
            return text
        except Exception:
            log.exception("Chit-chat problem")
            return None

    def say_now(self):
        """"Starling, talk to me": chat right away, ignoring the timers. Returns the text."""
        now = self.clock()
        mood = effective_mood(self.settings) or ""
        allow = bool(self.settings.get("speech.allow_mature", False))
        text = self._pick_text(now, mood, allow)
        if not text:
            return None
        text = personalise(text, self.settings)
        self.speech.say(text=text, priority="normal", event_name="chitchat")
        self.last_chat = self.last_spoke = now
        return text

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
