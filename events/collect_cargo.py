"""You scooped cargo."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class CollectCargo(BaseEvent):
    name = "CollectCargo"
    priority = LOW
    keep = ("Type",)
    summary = "Collected {Type}"
