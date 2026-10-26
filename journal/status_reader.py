"""
Watches Status.json, which the game rewrites about once a second while you play.

Lots of things are not journal events at all: landing gear, hardpoints, lights,
night vision, which screen you are looking at, low fuel... They are all
switches inside Status.json. STARLING compares the switches with last time and
announces the ones that just changed.

The list of switches lives in events/status_flags.py.
"""

import json
import time
from pathlib import Path

from core.event_bus import CRITICAL
from core.logger import get_logger
from events.status_flags import (
    FLAG_ROWS, FUEL_SCOOP_COMPLETE, MIN_ON_SECONDS, ROW_CONTEXT, SCREEN_CLOSED, SCREENS,
    SUPPRESS_IN_SUPERCRUISE, VEHICLE_CHANGED,
)

log = get_logger("status")

SCOOP_BIT = 1 << 11

# Handy names used by the demo and tests.
FLAG_LOW_FUEL = 1 << 19
FLAG_OVERHEATING = 1 << 20
FLAG_IN_DANGER = 1 << 22

# Minimum seconds between two announcements of the same warning,
# so a flickering flag cannot make her nag.
DEFAULT_MIN_GAP = {
    "LowFuel": 60, "Overheating": 30, "InDanger": 20,
    "InterdictionInProgress": 30, "MassLocked": 3, "MassLockReleased": 3,
}
_FALLBACK_GAP = 1.0

# If Status.json was last written longer ago than this when STARLING starts,
# the game is probably not running and the flags are old news.
STALE_SECONDS = 60


ENERGY_KEYS = ("SuitEnergy", "Energy", "SuitPower", "Power", "SuitBattery", "Battery")
_KNOWN_FOOT = {"Oxygen", "Health", "Temperature", "SelectedWeapon", "Gravity"}


def suit_energy(status):
    """Suit energy 0 to 1 if Status.json carries it, else None. The documented file does NOT list one; she looks for the
    usual names in case the game has added it (a value above 1 is read as a percentage)."""
    for key in ENERGY_KEYS:
        value = status.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            value = float(value)
            return value / 100.0 if value > 1.0 else value
    return None


class StatusReader:
    def __init__(self, folder, processor, min_gap_seconds=None):
        self.path = Path(folder) / "Status.json" if folder else None
        self.processor = processor
        if min_gap_seconds is None:
            self.min_gap = DEFAULT_MIN_GAP
            self._fallback_gap = _FALLBACK_GAP
        else:
            self.min_gap = min_gap_seconds
            self._fallback_gap = 0
        self._active = {}
        self._last_announced = {}
        self._signature = None
        self._first_read = True
        self._focus = None
        self._vehicle = None
        self._unknown_last = False
        self._on_since = {}
        self._suppressed = set()   # switches that changed while ignored (supercruise)
        self._tank_full_said = False
        self._fuel_said = set()       # which fuel warnings ("half", "panic") were already given for this tank
        self._clock = time.monotonic
        self.listeners = []         # functions called with the game state after every Status.json read (the biology distance check)

    # ---- watching the file ----
    def poll_once(self):
        if self.path is None:
            return
        try:
            info = self.path.stat()
        except OSError:
            return  # game not running, or no Status.json yet
        signature = (info.st_mtime_ns, info.st_size)
        if signature == self._signature:
            return
        self._signature = signature
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                status = json.load(handle)
        except (OSError, ValueError):
            self._signature = None  # the game was mid-write; try again next time
            return
        if not isinstance(status, dict):
            return
        old_file = (time.time() - info.st_mtime) > STALE_SECONDS
        self.handle_status(
            status,
            baseline_only=self._first_read and old_file,
            initial=self._first_read,
        )
        self._first_read = False

    # ---- working out what changed ----
    def handle_status(self, status, baseline_only=False, initial=False):
        """
        Compare the switches with last time and announce what changed.

        baseline_only: just remember the switches, announce nothing.
        initial:       first look at the file. Safety warnings are still
                       announced, but ordinary things (lights, gear...) are
                       not, so STARLING doesn't narrate your cockpit at start-up.

        Vehicle rule: when you change vehicle (ship to SRV, on foot, Nomad...)
        the game rewrites most switches at once. STARLING treats that moment as a
        fresh start instead of announcing every switch that changed.
        """
        flags = int(status.get("Flags") or 0)
        flags2 = int(status.get("Flags2") or 0)
        state = getattr(self.processor, "state", None)
        if state is not None:
            state.status_flags, state.status_flags2, state.status_seen = flags, flags2, flags != 0
            state.gui_focus = int(status.get("GuiFocus") or 0)
            state.selected_weapon = str(status.get("SelectedWeapon") or "")
            state.health = float(status["Health"]) if isinstance(status.get("Health"), (int, float)) else None
            state.suit_energy = suit_energy(status)
            self._log_foot_fields(status, flags2)
            dest = status.get("Destination")
            try:      # the body you have targeted (nav panel): the biology overlay follows it. No Destination = nothing targeted.
                state.bio.note_target(dest.get("Body") if isinstance(dest, dict) else None)
            except Exception:
                log.exception("Could not pass the target to the biology overlay")
            main = (status.get("Fuel") or {}).get("FuelMain")
            if isinstance(main, (int, float)):
                state.fuel_main = float(main)
            if isinstance(status.get("Cargo"), (int, float)):
                state.cargo_tons = float(status["Cargo"])
        if state is not None:
            near = all(isinstance(status.get(k), (int, float)) for k in ("Latitude", "Longitude", "PlanetRadius"))
            state.latitude = float(status["Latitude"]) if near else None
            state.longitude = float(status["Longitude"]) if near else None
            state.planet_radius = float(status["PlanetRadius"]) if near else None
            for listener in self.listeners:
                try:
                    listener(state)
                except Exception:
                    log.exception("A Status.json listener failed")
        if state is not None and isinstance(status.get("BodyName"), str) and status.get("BodyName"):
            state.current_body = status["BodyName"]       # present while you are near a planet
        vehicle = self._work_out_vehicle(flags, flags2)
        if vehicle == "main ship" and self._vehicle == "Nomad" and not baseline_only and not initial:
            self._announce("NomadDocked", status)             # the Nomad came home: the app puts the hardpoints away
        if vehicle == "main ship":
            self.processor.state.in_nomad = False   # back aboard: the Nomad is stowed

        # Flags are all zero in menus. Nothing to say, and the next real
        # reading must be treated as a fresh start.
        if vehicle is None:
            self._unknown_last = True
            for row in FLAG_ROWS:
                self._active[(row[0], row[1])] = False
            self._check_screen(status, quiet=True)
            return

        changed = self._vehicle is not None and vehicle != self._vehicle
        previous_vehicle = self._vehicle
        self._vehicle = vehicle
        fresh_start = baseline_only or changed or self._unknown_last
        self._unknown_last = False
        moving_fast = bool(flags & ((1 << 4) | (1 << 30)))  # supercruise or mid-jump
        self._check_fuel_levels(status, vehicle, flags, quiet=baseline_only or initial or fresh_start)

        # Fuel scooping: "complete" means the tank is full. It is said once per scoop,
        # and always BEFORE "scoop disengaged" if the tank filled as you left.
        scoop_now = bool(flags & SCOOP_BIT)
        scoop_was = self._active.get(("Flags", 11), False)
        if (not baseline_only and not initial and not fresh_start
                and vehicle == "main ship" and (scoop_now or scoop_was)
                and not self._tank_full_said and self._tank_is_full(status)):
            self._tank_full_said = True
            self._announce(FUEL_SCOOP_COMPLETE, status, self._fuel_details(status))
        if not scoop_now:
            self._tank_full_said = False

        for field, bit, on_name, on_text, on_prio, off_name, off_text, off_prio in FLAG_ROWS:
            value = flags if field == "Flags" else flags2
            now_on = bool(value & (1 << bit))
            key = (field, bit)
            was_on = self._active.get(key, False)
            self._active[key] = now_on
            if now_on and not was_on:
                self._on_since[key] = self._clock()
            if baseline_only:
                continue
            just_switched_on_critical = now_on and not was_on and on_prio == CRITICAL
            if fresh_start and not just_switched_on_critical:
                continue   # safety warnings are still announced on a fresh start
            allowed = ROW_CONTEXT.get(on_name)
            if allowed is not None and vehicle not in allowed:
                continue
            if on_name in SUPPRESS_IN_SUPERCRUISE:
                if moving_fast:
                    if now_on != was_on:
                        self._suppressed.add(key)
                    continue
                if key in self._suppressed and now_on != was_on:
                    continue   # the game flipped it during the jump; not news
            if now_on and not was_on:
                if initial and on_prio != CRITICAL:
                    continue
                self._announce(on_name, status)
            elif was_on and not now_on and off_name and off_text:
                needed = MIN_ON_SECONDS.get(off_name, 0)
                if needed and self._clock() - self._on_since.get(key, 0) < needed:
                    continue
                self._announce(off_name, status)

        if not moving_fast:
            self._suppressed.clear()
        if changed and not (baseline_only or initial):
            self._announce(VEHICLE_CHANGED, status, {"vehicle": vehicle, "previous": previous_vehicle})
        self._check_screen(status, quiet=baseline_only or initial)

    def _work_out_vehicle(self, flags, flags2):
        """Which vehicle are you in? None means unknown (for example, a menu)."""
        if flags & (1 << 24):
            return "main ship"
        if flags & (1 << 25):
            return "fighter"
        if flags & (1 << 26):
            # The game reports the Nomad as an SRV; the journal told us which one it is.
            return "Nomad" if self.processor.state.in_nomad else "SRV"
        if flags2 & 1:
            return "on foot"
        if flags or flags2:
            return "other vehicle"   # for example the Nomad
        return None

    def _check_fuel_levels(self, status, vehicle, flags, quiet):
        """A gentle nudge at 50 percent and a panic at 10. (The game's own low fuel warning, at 25 percent, is the one in between.)
        Each is said once per tank: they come back after you refuel above 60 percent. Never while docked or landed."""
        main = (status.get("Fuel") or {}).get("FuelMain")
        capacity = getattr(self.processor.state, "fuel_capacity", None)
        if vehicle != "main ship" or not isinstance(main, (int, float)) or not capacity:
            return
        percent = main / capacity * 100
        if percent > 60:
            self._fuel_said.clear()
        said = self._fuel_said
        name = "FuelPanic" if percent <= 10 else ("FuelHalf" if percent <= 50 else None)
        if name is None:
            return
        due = ["half", "panic"] if name == "FuelPanic" else ["half"]
        fresh = [tier for tier in due if tier not in said]
        said.update(due)
        docked = flags & ((1 << 0) | (1 << 1))                  # docked or landed
        if quiet or docked or not fresh or (name == "FuelHalf" and "panic" in said):
            return
        self._announce(name, status, {"fuel_percent": round(percent)})

    def _tank_is_full(self, status):
        fuel = status.get("Fuel") or {}
        main = fuel.get("FuelMain")
        capacity = self.processor.state.fuel_capacity
        return (isinstance(main, (int, float)) and bool(capacity)
                and main >= capacity - 0.1)

    @staticmethod
    def _fuel_details(status):
        main = (status.get("Fuel") or {}).get("FuelMain")
        return {"fuel_main": main, "fuel_percent": 100} if isinstance(main, (int, float)) else {}

    def _check_screen(self, status, quiet):
        focus = int(status.get("GuiFocus") or 0)
        previous = self._focus
        self._focus = focus
        if quiet or previous is None or focus == previous:
            return
        if focus == 0:
            if previous in SCREENS:
                self._announce(SCREEN_CLOSED, status, {"screen": SCREENS[previous][1]})
        elif focus in SCREENS:
            name, label = SCREENS[focus]
            self._announce(name, status, {"screen": label})

    def _announce(self, name, status, data=None):
        gap = self.min_gap.get(name, self._fallback_gap)
        last = self._last_announced.get(name)
        now = time.monotonic()
        if last is not None and now - last < gap:
            return
        self._last_announced[name] = now
        data = dict(data or {})
        if name == "LowFuel":
            fuel = status.get("Fuel") or {}
            main = fuel.get("FuelMain")
            if isinstance(main, (int, float)):
                data["fuel_main"] = main
                capacity = self.processor.state.fuel_capacity
                if capacity:
                    data["fuel_percent"] = round(main / capacity * 100)
        if name == "GlideStarted":
            data.update(self._body_facts())
        self.processor.emit(name, data)

    def _body_facts(self):
        """Temperature (kelvin) and gravity (g) of the planet you are gliding to, if a scan told us."""
        state = self.processor.state
        facts = (getattr(state, "bodies", None) or {}).get(getattr(state, "current_body", None))
        if not facts:
            return {}
        return {"temperature": int(round(facts["temperature"])), "gravity": "%.2f" % facts["gravity"],
                "heavy": facts["gravity"] >= 2.0}

    _foot_fields_logged = False

    def _log_foot_fields(self, status, flags2):
        """Once per run, write down every field Status.json has while you are on foot, so unknown ones (suit energy?) show up."""
        if self._foot_fields_logged or not (flags2 & 1):
            return
        self._foot_fields_logged = True
        extra = sorted(k for k in status if k not in _KNOWN_FOOT and k not in (
            "timestamp", "event", "Flags", "Flags2", "Pips", "Firegroup", "GuiFocus", "Fuel", "Cargo", "LegalState", "Latitude",
            "Altitude", "Longitude", "Heading", "BodyName", "PlanetRadius", "Balance", "Destination"))
        log.info("Status.json on foot has these fields: %s. Extra (not in the manual): %s. Suit energy field: %s",
                 ", ".join(sorted(status)), ", ".join(extra) or "none", "found" if suit_energy(status) is not None else "not found")
