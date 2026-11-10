"""SETTLEMENT RECORDER: writes down what the game tells us about each Odyssey settlement you visit, so we can work out how to
recognise a layout and how to place you on its map. It only LISTENS (journal lines and Status.json); it never touches the game.

For every visit it keeps (data/settlement_samples.json):
  * the settlement: name, economy, government, pad counts, the settlement's own coordinates (from ApproachSettlement)
  * your ship: the pad you were given, where it landed, which way it faced
  * a walking trail: your position and heading every 2 seconds while you are on foot near the settlement
  * marks you make by voice: "mark spot power regulator" stores the position with that label (stand at a feature first)
The file is small (the trail is capped) and goes into the diagnostics zip, so you can send it back.
"""
import json
import os
import re
import threading
import time
from datetime import datetime

from core import paths
from core.logger import get_logger

log = get_logger("settlement_recorder")

TRAIL_SECONDS = 2.0
TRAIL_MAX = 900                  # about 30 minutes on foot per visit
VISITS_MAX = 40
SAVE_SECONDS = 30.0
STARTS = ("ApproachSettlement",)
ENDS = ("SupercruiseEntry", "FSDJump", "Shutdown")
_MARK = re.compile(r"^(?:mark|record|log)\s+(?:this\s+)?(?:spot|place|position|location)(?:\s+(.+))?$")


def default_path():
    return paths.DATA_DIR / "settlement_samples.json"


class SettlementRecorder:
    def __init__(self, state_provider, path=None, clock=time.monotonic, stamp=None):
        self.state_provider = state_provider
        self.path = path or default_path()
        self.clock = clock
        self.stamp = stamp or (lambda: datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.visits = []
        self.current = None
        self._last_trail = -1e9
        self._last_save = 0.0
        self._dirty = False
        self.mark_hook = None            # (label, here) -> extra sentence: the map tracker uses marks to line the map up
        self._lock = threading.Lock()
        self._load()

    # ---- file ----
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, list):
                self.visits = [v for v in data if isinstance(v, dict)][-VISITS_MAX:]
        except (OSError, ValueError):
            self.visits = []

    def save(self):
        with self._lock:
            try:
                temp = str(self.path) + ".tmp"
                with open(temp, "w", encoding="utf-8") as handle:
                    json.dump(self.visits[-VISITS_MAX:], handle, indent=1)
                os.replace(temp, self.path)
                self._dirty = False
                self._last_save = self.clock()
            except OSError:
                log.exception("Could not save the settlement samples")

    def _touch(self, force=False):
        self._dirty = True
        if force or self.clock() - self._last_save >= SAVE_SECONDS:
            self.save()

    # ---- journal lines (called for every line, live only) ----
    def on_entry(self, entry, silent=False):
        if silent or not isinstance(entry, dict):
            return
        name = entry.get("event")
        try:
            if name in STARTS:
                self._begin(entry)
            elif name in ENDS and self.current is not None:
                self.current["ended"] = self.stamp()
                self.current = None
                self._touch(force=True)
            elif self.current is None and name == "Docked" and entry.get("StationType") == "OnFootSettlement":
                self._begin(dict(entry, Name=entry.get("StationName")))      # Starling was started after the approach: begin from the docking
                self._note(name, entry)
            elif self.current is not None:
                self._note(name, entry)
        except Exception:
            log.exception("The settlement recorder could not handle %s", name)

    def _begin(self, entry):
        keep = ("Name", "MarketID", "StationEconomy", "StationEconomies", "StationGovernment", "BodyName", "BodyID", "SystemAddress",
                "Latitude", "Longitude")
        visit = {"started": self.stamp(), "settlement": {k: entry[k] for k in keep if k in entry}, "journal": [], "marks": [], "trail": []}
        self.visits.append(visit)
        self.current = visit
        self._last_trail = -1e9
        self._touch(force=True)

    def _note(self, name, entry):
        visit = self.current
        if name in ("DockingRequested", "DockingGranted", "Docked", "Touchdown", "Liftoff", "Undocked", "Disembark", "Embark", "Location"):
            keep = ("LandingPads", "LandingPad", "StationType", "StationName", "Latitude", "Longitude", "NearestDestination", "OnStation",
                    "OnPlanet", "PlayerControlled", "BodyName", "DistFromStarLS")
            row = {"event": name, "time": entry.get("timestamp")}
            row.update({k: entry[k] for k in keep if k in entry})
            row["here"] = self._here()
            visit["journal"].append(row)
            if name == "Docked" and entry.get("StationType") == "OnFootSettlement":
                visit["settlement"].update({k: entry[k] for k in ("LandingPads", "StationEconomy") if k in entry})
            if name == "DockingGranted" and "LandingPad" in entry:
                visit["settlement"]["PadGiven"] = entry["LandingPad"]
            del visit["journal"][:-60]
            self._touch(force=True)

    def _here(self):
        state = self.state_provider()
        if state is None or getattr(state, "latitude", None) is None:
            return None
        return {"lat": state.latitude, "lon": state.longitude, "heading": getattr(state, "heading", None),
                "radius": getattr(state, "planet_radius", None)}

    # ---- Status.json (called after every read) ----
    def on_status(self, state):
        visit = self.current
        if visit is None or getattr(state, "latitude", None) is None:
            return
        now = self.clock()
        on_foot = bool(getattr(state, "status_flags2", 0) & 1)
        if on_foot and now - self._last_trail >= TRAIL_SECONDS and len(visit["trail"]) < TRAIL_MAX:
            self._last_trail = now
            visit["trail"].append([round(state.latitude, 7), round(state.longitude, 7), getattr(state, "heading", None),
                                   getattr(state, "altitude", None), getattr(state, "gui_focus", 0)])
            self._touch()
        elif self._dirty and now - self._last_save >= SAVE_SECONDS:
            self.save()

    # ---- voice: "mark spot power regulator" ----
    def try_handle(self, text):
        said = re.sub(r"[^a-z ]", " ", str(text or "").lower())
        said = re.sub(r"\s+", " ", said).strip()
        found = _MARK.match(said)
        if not found:
            return None
        if self.current is None:
            return "I am not at a settlement I know about, so I did not mark that spot."
        here = self._here()
        if here is None:
            return "I do not have your position yet, so I did not mark that spot."
        label = (found.group(1) or "").strip() or "spot %d" % (len(self.current["marks"]) + 1)
        self.current["marks"].append({"label": label, "time": self.stamp(), **here, "on_foot": bool(getattr(self.state_provider(), "status_flags2", 0) & 1)})
        self._touch(force=True)
        extra = None
        if self.mark_hook is not None:
            try:
                extra = self.mark_hook(label, here)
            except Exception:
                log.exception("The map could not use the marked spot")
        return ("Marked %s. %s" % (label, extra)) if extra else "Marked %s." % label
