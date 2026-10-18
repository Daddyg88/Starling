"""You refuelled at a station."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class RefuelAll(BaseEvent):
    name = "RefuelAll"
    priority = LOW
    keep = ("Amount", "Cost",)
    summary = "Refuelled {Amount:.1f} t"
