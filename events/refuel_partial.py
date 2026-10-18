"""You partly refuelled at a station."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class RefuelPartial(BaseEvent):
    name = "RefuelPartial"
    priority = LOW
    keep = ("Amount", "Cost",)
    summary = "Refuelled {Amount:.1f} t"
