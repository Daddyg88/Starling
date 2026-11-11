"""
HABITS: she notices what you keep doing, and says so. "Third time at Jameson Memorial this week." "That's the fourth time we've died in Sol."

It only listens to the event bus and keeps small counts in data/habits.json on YOUR computer (plain text; delete the file to start again).
She counts from the day she learned this, not from your whole career. Written at most every 30 seconds, and when she closes.

What she notices (each one is said at a calm moment, and never more than one habit remark every 20 minutes):
  * a station you dock at again and again          ("this is the 3rd time this week" at 3, 5, 8 and 12; "you practically live here" at 10, 25, 50, 100 landings)
  * a system where you keep dying                  ("the 3rd time we've been destroyed in Sol", said after you are back in a ship)
  * days in a row you have played                  (3, 7, 14, 30, 60, 100: said at the first calm moment after you log in)
  * jump milestones                                (100, 250, 500, 1000, 2500, 5000, 10000, 25000 jumps)
  * hours together                                 (5, 10, 25, 50, 100, 250, 500, 1000 hours: how well she knows you, see rapport())
The first time she runs, everything you have already passed is marked as told, so she does not announce a pile of old milestones at once.
Her words: voicepacks/default/habits.json. It also tells the chit-chat what to joke about (context()).
"""
import json
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta

from core.logger import get_logger

log = get_logger("habits")

SAVE_EVERY_SECONDS = 30.0
REMARK_GAP_SECONDS = 1200.0            # at most one habit remark in 20 minutes
WEEK_STEPS = (3, 5, 8, 12)             # dockings at the same station in the last 7 days
HOME_STEPS = (10, 25, 50, 100)         # dockings at the same station, ever
STREAK_STEPS = (3, 7, 14, 30, 60, 100)
JUMP_STEPS = (100, 250, 500, 1000, 2500, 5000, 10000, 25000)
HOUR_STEPS = (5, 10, 25, 50, 100, 250, 500, 1000)
MAX_STATIONS = 300                     # the most stations she remembers; the ones you have not been to for longest are dropped first
MAX_DOCK_DAYS = 40                     # recent landings kept per station
MAX_DAYS = 120                         # days played that she keeps
FAVOURITE_AT = 8                       # a station counts as your favourite after this many landings
MAX_NAME = 60

# rapport: how long you have flown together decides how well she knows you
RAPPORT_STAGES = ((1000.0, "family"), (100.0, "friend"), (25.0, "crew"), (0.0, "new"))


def rapport(hours):
    """'new' (under 25 hours together), 'crew' (25+), 'friend' (100+) or 'family' (1000+)."""
    try:
        hours = float(hours)
    except (TypeError, ValueError):
        return "new"
    for start, name in RAPPORT_STAGES:
        if hours >= start:
            return name
    return "new"


def ordinal(number):
    """1 -> '1st', 2 -> '2nd', 3 -> '3rd', 11 -> '11th'. (She says 'the 3rd time we have...')"""
    number = int(number)
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return "%d%s" % (number, suffix)


def passed(steps, value):
    """The biggest step that value has reached (0 if none)."""
    reached = 0
    for step in steps:
        if value >= step:
            reached = step
    return reached


def tidy_name(name):
    text = " ".join(str(name or "").split())
    return text[:MAX_NAME]


class HabitKeeper:
    def __init__(self, bus, path, announce=None, now=datetime.now, clock=time.monotonic, hours=None, jumps=None, enabled=None, system=None):
        self.bus, self.path, self.announce = bus, path, announce
        self.now, self.clock = now, clock
        self.hours = hours or (lambda: 0.0)               # () -> hours together, including this session
        self.jumps = jumps or (lambda: 0)                 # () -> jumps made in total
        self.enabled = enabled or (lambda: True)
        self.system = system or (lambda: None)           # () -> the system you are in now (a Died event does not say)
        self._lock = threading.RLock()
        self._dirty = False
        self._saved_at = -SAVE_EVERY_SECONDS
        self._last_remark = -REMARK_GAP_SECONDS
        self.stations = {}               # name -> {"count": n, "recent": ["2026-11-10", ...], "last": "2026-11-10"}
        self.deaths = {}                 # system -> how many times you were destroyed there
        self.days = []                   # days you played ("2026-11-10"), oldest first
        self.told = {"jumps": 0, "hours": 0, "streak": 0}
        self._death_system = None        # where you died, until you are back in a ship and she can mention it
        self._streak_waiting = 0         # a streak to mention at the next calm moment
        self._session_day = None
        fresh = not self._load()
        if fresh:
            self.told["jumps"] = passed(JUMP_STEPS, self._number(self.jumps))
            self.told["hours"] = passed(HOUR_STEPS, self._number(self.hours))
            self._dirty = True

    @staticmethod
    def _number(provider):
        try:
            return float(provider())
        except Exception:
            return 0.0

    # ---- wiring ----
    def attach(self):
        if self.bus is not None:
            self.bus.subscribe("*", self.on_event)

    def detach(self):
        if self.bus is not None:
            self.bus.unsubscribe("*", self.on_event)
        self.flush()

    # ---- the file ----
    def _load(self):
        """True when there was a file to read."""
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return False
        if not isinstance(data, dict):
            return False
        stations = data.get("stations")
        if isinstance(stations, dict):
            for name, entry in stations.items():
                if isinstance(entry, dict) and isinstance(entry.get("count"), int):
                    recent = [str(d) for d in (entry.get("recent") or []) if isinstance(d, str)][-MAX_DOCK_DAYS:]
                    self.stations[tidy_name(name)] = {"count": max(0, entry["count"]), "recent": recent, "last": str(entry.get("last", ""))}
        deaths = data.get("deaths")
        if isinstance(deaths, dict):
            self.deaths = {tidy_name(k): v for k, v in deaths.items() if isinstance(v, int) and v > 0}
        days = data.get("days")
        if isinstance(days, list):
            self.days = [d for d in days if isinstance(d, str)][-MAX_DAYS:]
        told = data.get("told")
        if isinstance(told, dict):
            for key in self.told:
                if isinstance(told.get(key), int) and told[key] >= 0:
                    self.told[key] = told[key]
        return True

    def flush(self):
        with self._lock:
            if not self._dirty:
                return
            data = {"stations": self.stations, "deaths": self.deaths, "days": self.days, "told": self.told}
            self._dirty = False
        try:
            folder = os.path.dirname(str(self.path)) or "."
            os.makedirs(folder, exist_ok=True)
            handle, temp = tempfile.mkstemp(dir=folder, suffix=".tmp")
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                json.dump(data, out)
            os.replace(temp, self.path)
        except OSError:
            log.exception("Could not save the habits")

    def _changed(self):
        self._dirty = True
        if self.clock() - self._saved_at >= SAVE_EVERY_SECONDS:
            self._saved_at = self.clock()
            self.flush()

    def today(self):
        return self.now().strftime("%Y-%m-%d")

    # ---- listening ----
    def on_event(self, event):
        try:
            if not self.enabled():
                return
            name, data = event.name, event.data or {}
            if name == "LoadGame":
                self._played_today()
            elif name == "Docked":
                self._docked(data)
            elif name == "Died":
                self._died(data)
            if name in ("Resurrect", "Location", "FSDJump", "Docked"):
                self._maybe_death_remark()
            if name == "FSDJump":
                self._milestones()
            if name in ("Docked", "FSDJump"):
                self._maybe_streak()
        except Exception:
            log.exception("The habit keeper could not note %s", getattr(event, "name", "?"))

    def _played_today(self):
        with self._lock:
            day = self.today()
            if self._session_day == day:
                return
            self._session_day = day
            if day not in self.days:
                self.days.append(day)
                self.days = self.days[-MAX_DAYS:]
            streak = self.streak()
            step = passed(STREAK_STEPS, streak)
            if step and step > self.told["streak"] and streak == step:
                self._streak_waiting = streak
            if streak < self.told["streak"]:
                self.told["streak"] = passed(STREAK_STEPS, streak)         # the run was broken: a new one can be remarked on again
            self._changed()

    def streak(self):
        """How many days in a row you have played, counting today."""
        with self._lock:
            if not self.days:
                return 0
            have = set(self.days)
            day = self.now().date()
            run = 0
            if day.strftime("%Y-%m-%d") not in have:
                day -= timedelta(days=1)
            while day.strftime("%Y-%m-%d") in have:
                run += 1
                day -= timedelta(days=1)
            return run

    def _docked(self, data):
        station = tidy_name(data.get("StationName"))
        if not station:
            return
        speak = None
        with self._lock:
            day = self.today()
            entry = self.stations.setdefault(station, {"count": 0, "recent": [], "last": day})
            entry["count"] += 1
            entry["recent"] = (entry["recent"] + [day])[-MAX_DOCK_DAYS:]
            entry["last"] = day
            week = self._in_last_week(entry["recent"])
            if entry["count"] in HOME_STEPS:
                speak = ("Habit_Station_Home", {"station": station, "count": entry["count"], "ordinal": ordinal(entry["count"])})
            elif week in WEEK_STEPS:
                speak = ("Habit_Station_Week", {"station": station, "count": week, "ordinal": ordinal(week)})
            self._trim()
            self._changed()
        if speak:
            self._say(*speak)

    def _in_last_week(self, recent):
        cutoff = (self.now().date() - timedelta(days=6)).strftime("%Y-%m-%d")
        return sum(1 for d in recent if d >= cutoff)

    def _trim(self):
        if len(self.stations) > MAX_STATIONS:
            oldest = sorted(self.stations, key=lambda k: self.stations[k].get("last", ""))[:len(self.stations) - MAX_STATIONS + 30]
            for key in oldest:
                self.stations.pop(key, None)

    def _died(self, data):
        system = tidy_name(data.get("StarSystem") or data.get("System") or self.system())
        with self._lock:
            if not system:
                return
            self.deaths[system] = self.deaths.get(system, 0) + 1
            if len(self.deaths) > 200:
                for key in sorted(self.deaths, key=self.deaths.get)[:50]:
                    self.deaths.pop(key, None)
            self._death_system = system
            self._changed()

    def _maybe_death_remark(self):
        with self._lock:
            system = self._death_system
            self._death_system = None
            count = self.deaths.get(system, 0) if system else 0
        if system and count >= 2:
            self._say("Habit_Death_Place", {"system": system, "count": count, "ordinal": ordinal(count)})

    def _maybe_streak(self):
        with self._lock:
            streak, self._streak_waiting = self._streak_waiting, 0
        if streak and self._say("Habit_Streak", {"days": streak}):
            with self._lock:
                self.told["streak"] = streak
                self._changed()

    def _milestones(self):
        with self._lock:
            jumps = int(self._number(self.jumps))
            hours = self._number(self.hours)
            jump_step, hour_step = passed(JUMP_STEPS, jumps), passed(HOUR_STEPS, hours)
            say_jumps = jump_step > self.told["jumps"]
            say_hours = hour_step > self.told["hours"]
        if say_jumps and self._say("Habit_Jumps", {"count": format(jump_step, ",")}, force=True):
            with self._lock:
                self.told["jumps"] = jump_step
                self._changed()
        elif say_hours and self._say("Rapport_Hours", {"hours": hour_step, "stage": rapport(hour_step)}, force=True):
            with self._lock:
                self.told["hours"] = hour_step
                self._changed()

    def _say(self, key, values, force=False):
        """One habit remark at most every 20 minutes (a milestone is rarer and ignores the gap, but still starts it)."""
        if self.announce is None:
            return False
        now = self.clock()
        if not force and now - self._last_remark < REMARK_GAP_SECONDS:
            return False
        try:
            said = self.announce(key, values)
        except Exception:
            log.exception("Could not say a habit remark")
            return False
        if said is False:
            return False
        self._last_remark = now
        return True

    def clear(self):
        """'Forget everything': the habits go too (the file is rewritten empty; what she has already told you stays told)."""
        with self._lock:
            self.stations, self.deaths, self.days = {}, {}, []
            self._death_system, self._streak_waiting = None, 0
            self.told = {"jumps": passed(JUMP_STEPS, self._number(self.jumps)), "hours": 0, "streak": 0}      # (hours together are wiped with it)
            self._dirty = True
        self.flush()

    # ---- what the chit-chat may joke about ----
    def favourite_station(self):
        """(name, landings) of the station you have docked at most, once that is FAVOURITE_AT or more; else None."""
        with self._lock:
            if not self.stations:
                return None
            name = max(self.stations, key=lambda k: self.stations[k]["count"])
            count = self.stations[name]["count"]
        return (name, count) if count >= FAVOURITE_AT else None

    def context(self):
        """Real facts she can mention in a chit-chat line (missing ones are left out so a line needing them is never used)."""
        values = {}
        favourite = self.favourite_station()
        if favourite:
            values["fav_station"], values["fav_count"] = favourite
        streak = self.streak()
        if streak >= 2:
            values["days_in_row"] = streak
        values["rapport"] = rapport(self._number(self.hours))
        return values
