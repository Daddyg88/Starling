"""Fleet carrier facts for the "plot a route to my carrier" command. None of these are spoken; they only update what she knows.

CarrierStats     your own carrier exists: its callsign (K7Q-B0Z style) tells us which carrier is yours
CarrierLocation  written when you load the game: which system your carrier is in
CarrierJump      the carrier you are aboard jumped (only counted when it is yours)
SquadronStartup  you are in a squadron
"""

import json
import re

from events.base_event import BaseEvent
from core.event_bus import LOW


def _text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


CALLSIGN = re.compile(r"^[A-Z0-9]{3}-[A-Z0-9]{3}$")


def looks_like_callsign(text):
    """A carrier serial such as K7Q-B0Z."""
    return bool(CALLSIGN.match((text or "").strip().upper()))


def is_own_carrier(entry, state):
    """True when this Docked/Location/CarrierJump entry is YOUR carrier: its callsign, its name, or its market id matches."""
    station = _text(entry.get("StationName"))
    if not station:
        return False
    callsign = _text(getattr(state, "fleet_carrier_callsign", None))
    name = _text(getattr(state, "fleet_carrier_name", None))
    if callsign and station.casefold() == callsign.casefold():
        return True
    if name and station.casefold() == name.casefold():
        return True
    carrier_id, market = getattr(state, "fleet_carrier_id", None), entry.get("MarketID")
    return bool(carrier_id and market and carrier_id == market and str(entry.get("StationType", "")).lower() == "fleetcarrier")


def spoken_station(entry, state):
    """What she should call this station: a carrier's NAME, never its serial, when the name is known."""
    station = _text(entry.get("StationName"))
    if station and (is_own_carrier(entry, state) or str(entry.get("StationType", "")).lower() == "fleetcarrier") and looks_like_callsign(station):
        if is_own_carrier(entry, state):
            return _text(getattr(state, "fleet_carrier_name", None)) or station
        return (getattr(state, "carrier_names", None) or {}).get(station.upper()) or station
    return station


MEMORY_FILE = None          # the app sets this to data/carrier.json so she still knows your carrier after a restart
_FIELDS = ("fleet_carrier_callsign", "fleet_carrier_name", "fleet_carrier_id", "fleet_carrier_system", "fleet_carrier_pos")
_last_saved = {}


def load_memory(state, path=None):
    """Put back what she knew about your carrier last time (only fills gaps; the journal always wins)."""
    path = path or MEMORY_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path else {}
    except (OSError, ValueError):
        return
    if not isinstance(data, dict):
        return
    for field in _FIELDS:
        value = data.get(field)
        if field == "fleet_carrier_pos":
            value = tuple(value) if isinstance(value, list) and len(value) == 3 else None
        if value and not getattr(state, field, None):
            setattr(state, field, value)
    _last_saved.clear()
    _last_saved.update({f: getattr(state, f, None) for f in _FIELDS})


def save_memory(state, path=None):
    """Write the carrier facts down when they changed (a few bytes, a few times a session)."""
    path = path or MEMORY_FILE
    if not path:
        return
    now = {f: getattr(state, f, None) for f in _FIELDS}
    if now == _last_saved:
        return
    try:
        path.write_text(json.dumps({f: (list(v) if isinstance(v, tuple) else v) for f, v in now.items()}), encoding="utf-8")
        _last_saved.clear()
        _last_saved.update(now)
    except OSError:
        pass


def _pos(entry):
    pos = entry.get("StarPos")
    if isinstance(pos, (list, tuple)) and len(pos) == 3:
        try:
            return tuple(float(v) for v in pos)
        except (TypeError, ValueError):
            return None
    return None


def carrier_label(state):
    """What she calls your carrier: its name, never the serial. None when the name is not known yet."""
    return _text(getattr(state, "fleet_carrier_name", None))


def remember_carrier_visit(entry, state):
    """Docked / Location / CarrierJump: if the station is YOUR carrier, then your carrier is in this system."""
    system = _text(entry.get("StarSystem"))
    if system and is_own_carrier(entry, state):
        if system != getattr(state, "fleet_carrier_system", None):
            state.fleet_carrier_pos = None
        state.fleet_carrier_system = system
        pos = _pos(entry)
        if pos:
            state.fleet_carrier_pos = pos
        save_memory(state)


class CarrierStats(BaseEvent):
    name = "CarrierStats"
    priority = LOW
    announce = False

    def update_state(self, entry, state):
        callsign = _text(entry.get("Callsign"))
        if callsign:
            state.fleet_carrier_callsign = callsign
        name = _text(entry.get("Name"))
        if name:
            state.fleet_carrier_name = name
        if entry.get("CarrierID"):
            state.fleet_carrier_id = entry.get("CarrierID")
        save_memory(state)


class CarrierLocation(BaseEvent):
    name = "CarrierLocation"
    priority = LOW
    announce = False

    def update_state(self, entry, state):
        system = _text(entry.get("StarSystem"))
        if system:
            if system != getattr(state, "fleet_carrier_system", None):
                state.fleet_carrier_pos = None
            state.fleet_carrier_system = system
            if system.casefold() == str(getattr(state, "system", "") or "").casefold() and getattr(state, "star_pos", None):
                state.fleet_carrier_pos = tuple(state.star_pos)
            save_memory(state)


class CarrierJump(BaseEvent):
    name = "CarrierJump"
    priority = LOW
    announce = False

    def update_state(self, entry, state):
        remember_carrier_visit(entry, state)
        state.bio.set_system(entry.get("StarSystem") or state.system)


class SquadronStartup(BaseEvent):
    name = "SquadronStartup"
    priority = LOW
    announce = False

    def update_state(self, entry, state):
        name = _text(entry.get("SquadronName"))
        if name:
            state.squadron = name
