"""
Mission reminders: she keeps a small list of the missions you take and speaks up at the right moment.

  * "Mission X runs out in 45 minutes" (once at 60 minutes left, once at 15), checked every minute while the game is running.
  * When you dock where a mission is due: "You have a mission with this station as its destination: X."

She only learns about missions you accept while she is running (the journal tells her the destination then), so a mission taken
before she started is not in her list. The list is kept in data/missions.json on your PC and cleaned up as missions finish, fail,
are abandoned or run out. It never touches the game.
"""
import json
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone

from core.logger import get_logger

log = get_logger("missions")

WARN_MINUTES = (60, 15)
CHECK_EVERY_SECONDS = 60.0
KEEP_AFTER_EXPIRY_MINUTES = 10
MAX_MISSIONS = 100
MAX_NAME = 60


def parse_expiry(text):
    """'2026-11-01T14:00:00Z' -> aware datetime, or None."""
    try:
        return datetime.strptime(str(text), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


class MissionReminder:
    def __init__(self, bus, settings, narrator, state_provider, path=None, now=lambda: datetime.now(timezone.utc), clock=time.monotonic):
        self.bus, self.settings, self.narrator, self.state_provider = bus, settings, narrator, state_provider
        self.path, self.now, self.clock = path, now, clock
        self.missions = {}                   # id -> {"name","expiry","system","station","warned":[minutes]}
        self._checked_at = -CHECK_EVERY_SECONDS
        self._load()

    # ---- wiring ----
    def attach(self):
        self.bus.subscribe("*", self.on_event)

    def detach(self):
        self.bus.unsubscribe("*", self.on_event)

    def enabled(self):
        return bool(self.settings.get("missions.reminders", True))

    # ---- file ----
    def _load(self):
        if not self.path:
            return
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return
        if isinstance(data, dict):
            self.missions = {str(k): v for k, v in data.items() if isinstance(v, dict)}

    def _save(self):
        if not self.path:
            return
        try:
            folder = os.path.dirname(str(self.path)) or "."
            os.makedirs(folder, exist_ok=True)
            handle, temp = tempfile.mkstemp(dir=folder, suffix=".tmp")
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                json.dump(self.missions, out)
            os.replace(temp, self.path)
        except OSError:
            log.exception("Could not save the mission list")

    # ---- events ----
    def on_event(self, event):
        try:
            name, data = event.name, event.data or {}
            if name == "MissionAccepted":
                self._accepted(data)
            elif name in ("MissionCompleted", "MissionFailed", "MissionAbandoned"):
                if self.missions.pop(str(data.get("MissionID")), None) is not None:
                    self._save()
            elif name == "MissionRedirected":
                mission = self.missions.get(str(data.get("MissionID")))
                if mission is not None:
                    mission["system"] = data.get("NewDestinationSystem") or ""
                    mission["station"] = data.get("NewDestinationStation") or ""
                    self._save()
            elif name == "Docked":
                self._docked(data)
            if self.enabled() and self.clock() - self._checked_at >= CHECK_EVERY_SECONDS:
                self._checked_at = self.clock()
                self.check_expiry()
        except Exception:
            log.exception("The mission reminder failed")

    def _accepted(self, data):
        mission_id = data.get("MissionID")
        if mission_id is None:
            return
        self.missions[str(mission_id)] = {
            "name": str(data.get("LocalisedName") or "")[:MAX_NAME], "expiry": str(data.get("Expiry") or ""),
            "system": str(data.get("DestinationSystem") or ""), "station": str(data.get("DestinationStation") or ""), "warned": []}
        if len(self.missions) > MAX_MISSIONS:
            for key in list(self.missions)[: len(self.missions) - MAX_MISSIONS]:
                self.missions.pop(key, None)
        self._save()

    # ---- speaking ----
    def check_expiry(self):
        """Warns about missions that are close to running out, and forgets missions that have run out."""
        now = self.now()
        changed = False
        for mission_id, mission in list(self.missions.items()):
            expiry = parse_expiry(mission.get("expiry"))
            if expiry is None:
                continue
            left = (expiry - now).total_seconds() / 60.0
            if left < -KEEP_AFTER_EXPIRY_MINUTES:
                self.missions.pop(mission_id, None)
                changed = True
                continue
            if left <= 0:
                continue
            due = [m for m in WARN_MINUTES if left <= m and m not in mission.get("warned", [])]
            if not due:
                continue
            mission["warned"] = sorted(set(mission.get("warned", [])) | {m for m in WARN_MINUTES if left <= m})
            changed = True
            self.narrator.say("Missions_Expiring", {"Name": mission.get("name") or "A mission", "Minutes": max(1, int(round(left)))})
            break                                                  # one at a time; the next is said a minute later
        if changed:
            self._save()

    def _docked(self, data):
        if not self.enabled():
            return
        station = str(data.get("StationName") or "")
        if not station:
            return
        here = [m for m in self.missions.values() if m.get("station") and m["station"].lower() == station.lower()]
        if not here:
            return
        if len(here) == 1:
            self.narrator.say("Missions_HandIn", {"Name": here[0].get("name") or "a mission"})
        else:
            self.narrator.say("Missions_HandInMany", {"Count": len(here)})
