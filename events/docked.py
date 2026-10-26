"""You docked at a station."""

from events.base_event import BaseEvent
from events.carriers import remember_carrier_visit
from core.event_bus import NORMAL


class Docked(BaseEvent):
    name = "Docked"
    priority = NORMAL
    keep = ("StationName", "StationType", "StarSystem", "Wanted", "StationServices",)
    summary = "Docked at {StationName} in {StarSystem}"

    def update_state(self, entry, state):
        state.docked = True
        if "Wanted" in entry:
            state.wanted = bool(entry["Wanted"])
        state.station = entry.get("StationName")
        state.system = entry.get("StarSystem") or state.system
        state.in_supercruise = False
        remember_carrier_visit(entry, state)
