"""You left supercruise."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class SupercruiseExit(BaseEvent):
    name = "SupercruiseExit"
    priority = LOW
    keep = ("StarSystem", "Body", "BodyType",)
    summary = "Dropped out of supercruise near {Body}"

    def update_state(self, entry, state):
        state.in_supercruise = False
        if entry.get("BodyType") in ("Planet", "Moon"):
            state.current_body = entry.get("Body") or state.current_body
