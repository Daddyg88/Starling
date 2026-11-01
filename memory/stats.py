"""
YOUR NUMBERS: how many times you have visited a system, kills, jumps and terraformable worlds found.

It only listens to the event bus (FSDJump, Bounty, FactionKillBond, Scan) and keeps small counts in data/stats.json on YOUR
computer (plain text; delete the file to start again). She counts from the day she learned this, not from your whole career:
the game journal for older days is not read. Written at most every 30 seconds, and when she closes.
"""
import json
import os
import tempfile
import threading
import time
from datetime import datetime

from core.logger import get_logger

log = get_logger("stats")

SAVE_EVERY_SECONDS = 30.0
MAX_SYSTEMS = 20000
MAX_BODIES = 5000
KILL_MILESTONES = (50, 100, 250, 500, 1000, 2500, 5000, 10000)


class StatsKeeper:
    def __init__(self, bus, path, announce=None, now=datetime.now, clock=time.monotonic):
        self.bus, self.path, self.announce = bus, path, announce
        self.now, self.clock = now, clock
        self._lock = threading.RLock()
        self._saved_at = -SAVE_EVERY_SECONDS
        self._dirty = False
        self.visits = {}                 # system -> {"count": n, "last": "2026-11-01"}
        self.kills_total = 0
        self.kills_by_day = {}
        self.jumps_total = 0
        self.jumps_by_day = {}
        self.terraformable = []          # body names, newest last
        self.session = {"kills": 0, "jumps": 0}
        self._load()

    # ---- wiring ----
    def attach(self):
        if self.bus is not None:
            self.bus.subscribe("*", self.on_event)

    def detach(self):
        if self.bus is not None:
            self.bus.unsubscribe("*", self.on_event)
        self.flush()

    # ---- reading and writing the file ----
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        visits = data.get("visits")
        self.visits = {str(k): v for k, v in visits.items() if isinstance(v, dict)} if isinstance(visits, dict) else {}
        for name in ("kills_total", "jumps_total"):
            value = data.get(name)
            setattr(self, name, value if isinstance(value, int) and value >= 0 else 0)
        for name in ("kills_by_day", "jumps_by_day"):
            value = data.get(name)
            setattr(self, name, {str(k): v for k, v in value.items() if isinstance(v, int)} if isinstance(value, dict) else {})
        bodies = data.get("terraformable")
        self.terraformable = [str(b) for b in bodies][-MAX_BODIES:] if isinstance(bodies, list) else []

    def flush(self):
        with self._lock:
            if not self._dirty:
                return
            data = {"visits": self.visits, "kills_total": self.kills_total, "kills_by_day": self.kills_by_day,
                    "jumps_total": self.jumps_total, "jumps_by_day": self.jumps_by_day, "terraformable": self.terraformable}
            self._dirty = False
        try:
            folder = os.path.dirname(str(self.path)) or "."
            os.makedirs(folder, exist_ok=True)
            handle, temp = tempfile.mkstemp(dir=folder, suffix=".tmp")
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                json.dump(data, out)
            os.replace(temp, self.path)
        except OSError:
            log.exception("Could not save the numbers")

    def _changed(self):
        self._dirty = True
        if self.clock() - self._saved_at >= SAVE_EVERY_SECONDS:
            self._saved_at = self.clock()
            self.flush()

    def today(self):
        return self.now().strftime("%Y-%m-%d")

    # ---- counting ----
    def on_event(self, event):
        try:
            name, data = event.name, event.data or {}
            if name == "FSDJump":
                self._jump(data.get("StarSystem"))
            elif name in ("Bounty", "FactionKillBond"):
                self._kill()
            elif name == "Scan":
                self._scan(data)
        except Exception:
            log.exception("Counting an event failed")

    def _jump(self, system):
        with self._lock:
            day = self.today()
            self.jumps_total += 1
            self.jumps_by_day[day] = self.jumps_by_day.get(day, 0) + 1
            self.session["jumps"] += 1
            if system:
                entry = self.visits.setdefault(str(system), {"count": 0, "last": ""})
                entry["previous"] = entry.get("last", "")
                entry["count"] = int(entry.get("count", 0)) + 1
                entry["last"] = day
                if len(self.visits) > MAX_SYSTEMS:
                    oldest = sorted(self.visits, key=lambda k: self.visits[k].get("last", ""))[:1000]
                    for key in oldest:
                        self.visits.pop(key, None)
            if len(self.jumps_by_day) > 400:
                for key in sorted(self.jumps_by_day)[:100]:
                    self.jumps_by_day.pop(key, None)
            self._changed()

    def _kill(self):
        with self._lock:
            day = self.today()
            self.kills_total += 1
            self.kills_by_day[day] = self.kills_by_day.get(day, 0) + 1
            self.session["kills"] += 1
            if len(self.kills_by_day) > 400:
                for key in sorted(self.kills_by_day)[:100]:
                    self.kills_by_day.pop(key, None)
            total = self.kills_total
            self._changed()
        if total in KILL_MILESTONES and self.announce is not None:
            try:
                self.announce("Stats_KillMilestone", {"Number": "{:,}".format(total)})
            except Exception:
                log.exception("Could not announce a kill milestone")

    def _scan(self, data):
        body = data.get("BodyName")
        if body and str(data.get("TerraformState") or "").lower().startswith("terraform"):
            with self._lock:
                if str(body) not in self.terraformable:
                    self.terraformable.append(str(body))
                    self.terraformable = self.terraformable[-MAX_BODIES:]
                    self._changed()

    # ---- questions ----
    def visit_info(self, system):
        """(count, last visit before this one or '') for a system, or (0, '')."""
        entry = self.visits.get(str(system or ""))
        if not entry:
            return 0, ""
        return int(entry.get("count", 0)), str(entry.get("previous") or "")

    def kills_today(self):
        return self.kills_by_day.get(self.today(), 0)

    def jumps_today(self):
        return self.jumps_by_day.get(self.today(), 0)
