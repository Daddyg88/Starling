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
from pathlib import Path
import time
from datetime import datetime

from core.logger import get_logger

log = get_logger("stats")

SAVE_EVERY_SECONDS = 30.0
MAX_SYSTEMS = 5000              # the most systems she keeps; the ones you have not seen for longest are dropped first
TRIM_BY = 500
REVISIT_COOLDOWN = 600.0        # seconds between 'we've been here' remarks
MAX_SCANNED = 999
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
        self.history_done = False
        self.previous = {}               # how the last play session ended: {"ended": "2026-11-08", "jumps": n, "kills": n}
        self._recap_given = False
        self._here = ""
        self._revisit_at = -REVISIT_COOLDOWN
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
        self.history_done = bool(data.get("history_done", False))
        last = data.get("last_session")
        if isinstance(last, dict):
            self.previous = {"ended": str(last.get("ended", "")), "jumps": int(last.get("jumps", 0) or 0), "kills": int(last.get("kills", 0) or 0)}
        bodies = data.get("terraformable")
        self.terraformable = [str(b) for b in bodies][-MAX_BODIES:] if isinstance(bodies, list) else []

    def flush(self):
        with self._lock:
            if not self._dirty:
                return
            data = {"visits": self.visits, "kills_total": self.kills_total, "kills_by_day": self.kills_by_day,
                    "jumps_total": self.jumps_total, "jumps_by_day": self.jumps_by_day, "terraformable": self.terraformable, "history_done": self.history_done}
            if self.session["jumps"] or self.session["kills"]:          # this session becomes "last time" for the next start
                data["last_session"] = {"ended": self.today(), "jumps": self.session["jumps"], "kills": self.session["kills"]}
            elif self.previous:
                data["last_session"] = self.previous
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

    def recap(self):
        """What the last play session was, ONCE per start: {"when": "yesterday", "summary": "18 jumps and 3 kills"} or None.
        Nothing when there is no record, it was empty, or it is more than 60 days old."""
        with self._lock:
            if self._recap_given or not self.previous:
                return None
            self._recap_given = True
            jumps, kills = self.previous.get("jumps", 0), self.previous.get("kills", 0)
            try:
                days = (self.now().date() - datetime.strptime(self.previous.get("ended", ""), "%Y-%m-%d").date()).days
            except ValueError:
                return None
        if days < 0 or days > 60 or not (jumps or kills):
            return None
        parts = []
        if jumps:
            parts.append("%d jump%s" % (jumps, "" if jumps == 1 else "s"))
        if kills:
            parts.append("%d kill%s" % (kills, "" if kills == 1 else "s"))
        when = "earlier today" if days == 0 else "yesterday" if days == 1 else "%d days ago" % days
        return {"when": when, "summary": " and ".join(parts)}

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
            elif name in ("Location", "CarrierJump"):
                self._here = str(data.get("StarSystem") or self._here)
        except Exception:
            log.exception("Counting an event failed")

    def _jump(self, system):
        speak = None
        with self._lock:
            day = self.today()
            self.jumps_total += 1
            self.jumps_by_day[day] = self.jumps_by_day.get(day, 0) + 1
            self.session["jumps"] += 1
            if system:
                self._here = str(system)
                entry = self.visits.setdefault(str(system), {"count": 0, "last": ""})
                been = int(entry.get("count", 0)) >= 1 or int(entry.get("scanned", 0)) >= 1
                entry["previous"] = entry.get("last", "")
                entry["count"] = int(entry.get("count", 0)) + 1
                entry["last"] = day
                if been and self.clock() - self._revisit_at >= REVISIT_COOLDOWN:
                    self._revisit_at = self.clock()
                    last = entry["previous"]
                    speak = (str(system), entry["count"], int(entry.get("scanned", 0)),
                             (" The last time was on %s." % last) if last else "")
                self._trim()
            if len(self.jumps_by_day) > 400:
                for key in sorted(self.jumps_by_day)[:100]:
                    self.jumps_by_day.pop(key, None)
            self._changed()
        if speak and self.announce is not None:
            try:
                name, count, bodies, last = speak
                self.announce("Stats_Revisit_Scanned" if bodies else "Stats_Revisit",
                              {"System": name, "Count": count, "Bodies": bodies, "Last": last})
            except Exception:
                log.exception("Could not say we have been here before")

    def _trim(self):
        """Keeps the list from growing for ever: past the cap, the 500 systems seen longest ago are forgotten."""
        if len(self.visits) > MAX_SYSTEMS:
            oldest = sorted(self.visits, key=lambda k: self.visits[k].get("last", ""))[:TRIM_BY]
            for key in oldest:
                self.visits.pop(key, None)

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
        system = str(data.get("StarSystem") or self._here or "")
        if system and data.get("ScanType") != "NavBeaconDetail":
            with self._lock:
                entry = self.visits.setdefault(system, {"count": 0, "last": self.today()})
                entry["scanned"] = min(MAX_SCANNED, int(entry.get("scanned", 0)) + 1)
                self._trim()
                self._changed()

    # ---- reading the old journals once ----
    def seed(self, found):
        """Adds what the old journals say: {system: (visits, last day, scanned bodies)}. Never lowers what she already counted."""
        with self._lock:
            for system, (count, last, scanned) in found.items():
                entry = self.visits.setdefault(system, {"count": 0, "last": ""})
                entry["count"] = max(int(entry.get("count", 0)), int(count))
                entry["last"] = max(str(entry.get("last", "")), str(last))
                entry["scanned"] = min(MAX_SCANNED, max(int(entry.get("scanned", 0)), int(scanned)))
            while len(self.visits) > MAX_SYSTEMS:
                self._trim()
            self.history_done = True
            self._dirty = True
        self.flush()

    def scan_history(self, folder):
        """Once, in the background: which systems you have been in and scanned, from your old journals (a few lines per file)."""
        if self.history_done or not folder:
            return
        found = {}
        tags = (b'"event":"FSDJump"', b'"event":"CarrierJump"', b'"event":"Scan"')
        try:
            files = sorted(Path(folder).glob("Journal*.log"))
        except OSError:
            return
        for file in files:
            here = ""
            try:
                with open(file, "rb") as handle:
                    for raw in handle:
                        if not any(tag in raw for tag in tags):
                            continue
                        try:
                            entry = json.loads(raw)
                        except ValueError:
                            continue
                        kind, day = entry.get("event"), str(entry.get("timestamp") or "")[:10]
                        if kind in ("FSDJump", "CarrierJump"):
                            here = str(entry.get("StarSystem") or "")
                            if here:
                                old = found.get(here, (0, "", 0))
                                found[here] = (old[0] + 1, max(old[1], day), old[2])
                        elif kind == "Scan" and entry.get("ScanType") != "NavBeaconDetail":
                            name = str(entry.get("StarSystem") or here)
                            if name:
                                old = found.get(name, (0, "", 0))
                                found[name] = (old[0], max(old[1], day), old[2] + 1)
            except OSError:
                continue
            time.sleep(0.02)
        if len(found) > MAX_SYSTEMS:                      # keep only the newest ones
            keep = sorted(found, key=lambda k: found[k][1], reverse=True)[:MAX_SYSTEMS]
            found = {k: found[k] for k in keep}
        self.seed(found)
        log.info("Learned %d systems from the old journals", len(found))

    # ---- questions ----
    def visit_info(self, system):
        """(count, last visit before this one or '') for a system, or (0, '')."""
        entry = self.visits.get(str(system or ""))
        if not entry:
            return 0, ""
        return int(entry.get("count", 0)), str(entry.get("previous") or "")

    def scanned_here(self, system):
        """How many bodies you have scanned in this system (0 if none or unknown)."""
        return int((self.visits.get(str(system or "")) or {}).get("scanned", 0))

    def kills_today(self):
        return self.kills_by_day.get(self.today(), 0)

    def jumps_today(self):
        return self.jumps_by_day.get(self.today(), 0)
