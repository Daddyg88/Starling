"""You came close to a settlement."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class ApproachSettlement(BaseEvent):
    name = "ApproachSettlement"
    priority = LOW
    keep = ("Name",)
    summary = "Approaching {Name}"
