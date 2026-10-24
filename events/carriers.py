"""Fleet carrier facts for the "plot a route to my carrier" command. None of these are spoken; they only update what she knows.

CarrierStats     your own carrier exists: its callsign (K7Q-B0Z style) tells us which carrier is yours
CarrierLocation  written when you load the game: which system your carrier is in
CarrierJump      the carrier you are aboard jumped (only counted when it is yours)
SquadronStartup  you are in a squadron
"""

from events.base_event import BaseEvent
from core.event_bus import LOW


def _text(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


def remember_carrier_visit(entry, state):
    """Docked / Location / CarrierJump: if the station is YOUR carrier, then your carrier is in this system."""
    callsign = _text(getattr(state, "fleet_carrier_callsign", None))
    station = _text(entry.get("StationName"))
    system = _text(entry.get("StarSystem"))
    if callsign and station and system and station.casefold() == callsign.casefold():
        state.fleet_carrier_system = system


class CarrierStats(BaseEvent):
    name = "CarrierStats"
    priority = LOW
    announce = False

    def update_state(self, entry, state):
        callsign = _text(entry.get("Callsign"))
        if callsign:
            state.fleet_carrier_callsign = callsign


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


class SquadronStartup(BaseEvent):
    name = "SquadronStartup"
    priority = LOW
    announce = False

    def update_state(self, entry, state):
        name = _text(entry.get("SquadronName"))
        if name:
            state.squadron = name
