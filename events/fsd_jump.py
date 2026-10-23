"""You arrived in a new system."""

from events.base_event import BaseEvent
from events.system_facts import remember_system_facts
import random

from core.event_bus import NORMAL

JUMPS_LEFT_CHANCE = 0.3       # how often she mentions how many jumps are left


class FSDJump(BaseEvent):
    name = "FSDJump"
    priority = NORMAL
    keep = ("StarSystem", "JumpDist", "FuelUsed", "FuelLevel", "StarClass", "Wanted",)
    summary = "Jumped to {StarSystem} ({JumpDist:.1f} ly)"

    def update_state(self, entry, state):
        state.system = entry.get("StarSystem") or state.system
        state.wanted = bool(entry.get("Wanted", False))
        remember_system_facts(entry, state)
        state.docked = False
        state.station = None
        state.in_supercruise = True
        state.awaiting_discovery = True
        left, state.route_jumps_left = state.route_jumps_left, None
        if isinstance(left, int) and left >= 1 and (left == 1 or random.random() < JUMPS_LEFT_CHANCE):
            state.pending_events.append(("JumpsLeft", {"jumps": left, "last": left == 1}))
