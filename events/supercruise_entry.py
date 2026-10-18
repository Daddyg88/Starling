"""You entered supercruise."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class SupercruiseEntry(BaseEvent):
    name = "SupercruiseEntry"
    priority = LOW
    keep = ("StarSystem",)
    summary = "Entered supercruise in {StarSystem}"

    def update_state(self, entry, state):
        state.in_supercruise = True
