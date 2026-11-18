"""Fleet carrier facts for the "plot a route to my carrier" command. None of these are spoken; they only update what she knows.

CarrierStats     your own carrier exists: its callsign (K7Q-B0Z style) tells us which carrier is yours
CarrierLocation  written when you load the game: which system your carrier is in
CarrierJump      the carrier you are aboard jumped (only counted when it is yours)
SquadronStartup  you are in a squadron
"""

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


def remember_carrier_visit(entry, state):
    """Docked / Location / CarrierJump: if the station is YOUR carrier, then your carrier is in this system."""
    system = _text(entry.get("StarSystem"))
    if system and is_own_carrier(entry, state):
        state.fleet_carrier_system = system


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


class CarrierLocation(BaseEvent):
    name = "CarrierLocation"
    priority = LOW
    announce = False

    def update_state(self, entry, state):
        system = _text(entry.get("StarSystem"))
        if system:
            state.fleet_carrier_system = system


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
