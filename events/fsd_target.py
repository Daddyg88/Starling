"""You selected the next jump target."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class FSDTarget(BaseEvent):
    name = "FSDTarget"
    priority = LOW
    keep = ("Name", "RemainingJumpsInRoute",)
    summary = "Next jump target: {Name}"

    def update_state(self, entry, state):
        left = entry.get("RemainingJumpsInRoute")
        state.route_jumps_left = int(left) if isinstance(left, (int, float)) else None
