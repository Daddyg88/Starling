"""
Where you are when the game loads (it follows LoadGame in the journal).
It is not spoken by itself; the login greeting uses it to say where you are.
"""

from events.base_event import BaseEvent
from events.system_facts import remember_star_pos, remember_system_facts
from events.carriers import remember_carrier_visit
from core.event_bus import LOW


class Location(BaseEvent):
    name = "Location"
    priority = LOW
    keep = ("StarSystem", "Docked", "StationName", "StationType", "Body", "BodyType", "Wanted",)
    summary = "Location: {StarSystem}"

    def handle(self, entry):
        data = super().handle(entry)
        docked = bool(entry.get("Docked", False))
        data["Docked"] = docked
        # Landed on a planet's surface: the game gives a latitude when you are not docked.
        data["Landed"] = (not docked) and ("Latitude" in entry) and not entry.get("OnFoot", False)
        return data

    def update_state(self, entry, state):
        state.system = entry.get("StarSystem") or state.system
        state.bio.set_system(state.system)
        if state.owned.has(state.system):
            state.pending_events.append(("OwnSystemArrival", {"StarSystem": state.system}))
        state.wanted = bool(entry.get("Wanted", False))
        remember_system_facts(entry, state)
        remember_star_pos(entry, state)
        state.docked = bool(entry.get("Docked", False))
        state.station = entry.get("StationName") if state.docked else None
        remember_carrier_visit(entry, state)
