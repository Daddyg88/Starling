"""You came close to a planet or moon."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class ApproachBody(BaseEvent):
    name = "ApproachBody"
    priority = LOW
    keep = ("Body", "StarSystem",)
    summary = "Approaching {Body}"

    def update_state(self, entry, state):
        state.current_body = entry.get("Body") or state.current_body
