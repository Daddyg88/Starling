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
from core.ships import ship_name
from core.logger import get_logger
from personality.mood_engine import effective_mood

log = get_logger("chitchat")

# frequency -> (seconds of silence needed, minimum seconds between two chats)
FREQUENCY = {"rarely": (600.0, 1500.0), "normal": (150.0, 360.0), "often": (90.0, 210.0), "chatty": (50.0, 120.0)}
MINING_EVENTS = ("ProspectedAsteroid", "MiningRefined", "AsteroidCracked")
MINING_SECONDS = 600.0           # she talks about mining for 10 minutes after the last mining event
ALARMS = ("UnderAttack", "Interdicted", "InterdictionInProgress", "LowFuel", "Overheating", "HeatWarning", "HeatDamage",
          "HullDamage", "InDanger", "LowHealth", "LowOxygen", "Died", "CockpitBreached", "ShieldState")
ALARM_QUIET_SECONDS = 75.0
STATE_KEYS = ("ChitChat_Hull", "ChitChat_Wanted", "ChitChat_Long", "ChitChat_Callback_Interdicted", "ChitChat_Callback_Kill")
CALLBACK_AFTER_SECONDS = 600.0      # she looks back on a moment from 10 minutes to 90 minutes ago
CALLBACK_UNTIL_SECONDS = 5400.0
STATE_REST = 1200.0              # and says the same kind of remark at most once in 20 minutes
HULL_REMARK = 0.8                # below this much hull she mentions it (when it is quiet)
CHECK_EVERY_SECONDS = 15.0

# NOTICING (0.89.0): she counts things during the session and, at a quiet moment, remarks when a count passes a step.
# (pool, counter name, step, only worth saying for this long after it happened). Kills may also be remarked on in combat mode.
MILESTONES = (
    ("ChitChat_Kills", "kills", 5, 600.0),
    ("ChitChat_Interdicted", "interdictions", 2, 900.0),
    ("ChitChat_Scans", "scans", 25, 900.0),
    ("ChitChat_Systems", "systems", 10, 900.0),
    ("ChitChat_NoScoop", "since_scoop", 8, 600.0),
)


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
        self.last_mining = None
        self.state_said = {}             # when she last made each state remark (hull, bounty, long session)
        self.counts = {"kills": 0, "interdictions": 0, "scans": 0, "systems": 0, "since_scoop": 0}
        self.systems_seen = set()
        self.last_moment = {}            # "interdicted" / "kill" -> (when, system it happened in): for looking back on it later
        self.reached = {}                # pool -> (level reached, when): a milestone waiting to be remarked on
        self.remarked = {}               # pool -> the level she last remarked on

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
            self._count("since_scoop", self.counts["since_scoop"] + 1, now)
            system = (event.data or {}).get("StarSystem")
            if system and system not in self.systems_seen:
                self.systems_seen.add(system)
                self._count("systems", len(self.systems_seen), now)
            dist = (event.data or {}).get("JumpDist")
            if isinstance(dist, (int, float)) and dist > 0:
                self.distance += float(dist)
        elif name in MINING_EVENTS:
            self.last_mining = now
        elif name in ("Bounty", "FactionKillBond"):
            self._count("kills", self.counts["kills"] + 1, now)
            self._remember_moment("kill", now)
        elif name == "Interdicted":
            self._count("interdictions", self.counts["interdictions"] + 1, now)
            self._remember_moment("interdicted", now)
        elif name == "Scan":
            self._count("scans", self.counts["scans"] + 1, now)
        elif name == "FuelScoop":
            self.counts["since_scoop"] = 0
        elif name == "CombatModeOn":
            self.mode = "combat"
        elif name == "AnalysisModeOn":
            self.mode = "analysis"
        elif name in ALARMS:
            self.last_alarm = now

    def _count(self, name, value, now):
        """Sets a counter and notes when it passes a step, so she can remark on it at the next quiet moment."""
        self.counts[name] = value
        if not self.settings.get("chitchat.notice", True):
            return
        for pool, counter, step, _fresh in MILESTONES:
            if counter == name and step > 0 and value // step > 0:
                self.reached[pool] = (value // step, now)

    def _remember_moment(self, what, now):
        system = getattr(self.state_provider(), "system", None)
        if system:
            self.last_moment[what] = (now, str(system))

    def milestone_keys(self, now=None):
        """Pools for counts that passed a step recently and have not been remarked on yet."""
        now = self.clock() if now is None else now
        if not self.settings.get("chitchat.notice", True):
            return []
        found = []
        for pool, _counter, _step, fresh in MILESTONES:
            level, when = self.reached.get(pool, (0, 0.0))
            if level > self.remarked.get(pool, 0) and now - when <= fresh:
                found.append(pool)
        return found

    # ---- deciding ----
    def _timing(self):
        quiet, gap = FREQUENCY.get(str(self.settings.get("chitchat.frequency", "normal")), FREQUENCY["normal"])
        if self.mode == "combat":
            quiet = quiet / 2.0                     # a fight is livelier; she may chip in a little sooner
        if self.mining_now():
            quiet, gap = quiet * 0.5, gap * 0.6     # mining is long and quiet: she keeps you company more often
        return quiet, gap

    def mining_now(self):
        return self.last_mining is not None and self.clock() - self.last_mining < MINING_SECONDS

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
        notice = self.milestone_keys()
        if self.mode == "combat":
            return (["ChitChat_Kills"] if "ChitChat_Kills" in notice else []) + ["ChitChat_Combat"]
        extra = notice + self.state_keys(state)
        if extra:
            return extra + self._normal_keys(state, docked)
        return self._normal_keys(state, docked)

    def state_keys(self, state):
        """Things worth bringing up because of what is true right now (a damaged hull, a bounty, a long session)."""
        keys = []
        hull = getattr(state, "hull_health", None)
        if isinstance(hull, (int, float)) and 0.0 < hull < HULL_REMARK:
            keys.append("ChitChat_Hull")
        if getattr(state, "wanted", False) is True:
            keys.append("ChitChat_Wanted")
        if int((self.clock() - self.started) / 3600) >= 2:
            keys.append("ChitChat_Long")
        now = self.clock()
        if self.settings.get("chitchat.notice", True):
            for what, key in (("interdicted", "ChitChat_Callback_Interdicted"), ("kill", "ChitChat_Callback_Kill")):
                moment = self.last_moment.get(what)
                if moment and CALLBACK_AFTER_SECONDS <= now - moment[0] <= CALLBACK_UNTIL_SECONDS and moment[1] != getattr(state, "system", None):
                    keys.append(key)                         # (only when you have moved on: "back in X", not "right here")
        return [k for k in keys if now - self.state_said.get(k, -STATE_REST) >= STATE_REST]

    def _normal_keys(self, state, docked):
        if docked:
            return ["ChitChat_Docked", "ChitChat_Flying"]
        if self.last_mining is not None and self.clock() - self.last_mining < MINING_SECONDS:
            return ["ChitChat_Mining"]
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
            values["ship"] = ship_name(ship)
        if getattr(state, "system", None):
            values["system"] = state.system
        if getattr(state, "docked", False) and getattr(state, "station", None):
            values["station"] = state.station
        if self.jumps >= 3:
            values["jumps"] = self.jumps
        if self.distance >= 50:
            values["distance"] = int(round(self.distance))
        hull = getattr(state, "hull_health", None)
        if isinstance(hull, (int, float)) and 0.0 < hull < HULL_REMARK:
            values["hull"] = int(round(hull * 100))
        values["hours"] = int((now - self.started) / 3600) if now - self.started >= 7200 else None
        if values["hours"] is None:
            del values["hours"]
        minutes = int((now - self.started) / 60)
        if minutes >= 20:
            values["minutes"] = minutes
        if "interdicted" in self.last_moment:
            values["interdict_system"] = self.last_moment["interdicted"][1]
        if "kill" in self.last_moment:
            values["kill_system"] = self.last_moment["kill"][1]
        for name in ("kills", "interdictions", "scans", "systems", "since_scoop"):
            if self.counts.get(name, 0) > 0:
                values[name] = self.counts[name]
        return values

    def _pick_text(self, now, mood, allow):
        values = self.context(now)
        keys = list(self.candidate_keys())
        first = [k for k in keys if k in self.reached and k in self.milestone_keys(now)]       # something she noticed comes first
        rest = [k for k in keys if k not in first]
        self.rng.shuffle(rest)
        keys = first + rest
        keys.append("ChitChat_General")
        for key in keys:
            for _ in range(6):
                line = self.dialogue.pick(key, mood, allow, False)
                if line is None:
                    break
                try:
                    text = line.text.format(**values)       # needs every value it mentions
                    if key in STATE_KEYS:
                        self.state_said[key] = now
                    if key in self.reached:
                        self.remarked[key] = self.reached[key][0]       # said: the next remark waits for the next step
                    return text
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
