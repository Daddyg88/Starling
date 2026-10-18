"""You moved away from a planet or moon."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class LeaveBody(BaseEvent):
    name = "LeaveBody"
    priority = LOW
    keep = ("Body",)
    summary = "Leaving {Body}"
