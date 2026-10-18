"""You arrived in a new system."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class FSDJump(BaseEvent):
    name = "FSDJump"
    priority = NORMAL
    keep = ("StarSystem", "JumpDist", "FuelUsed", "FuelLevel", "StarClass", "Wanted",)
    summary = "Jumped to {StarSystem} ({JumpDist:.1f} ly)"

    def update_state(self, entry, state):
        state.system = entry.get("StarSystem") or state.system
        state.wanted = bool(entry.get("Wanted", False))
        state.docked = False
        state.station = None
        state.in_supercruise = True
