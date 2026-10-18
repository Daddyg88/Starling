"""You came close to a planet or moon."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class ApproachBody(BaseEvent):
    name = "ApproachBody"
    priority = LOW
    keep = ("Body", "StarSystem",)
    summary = "Approaching {Body}"
