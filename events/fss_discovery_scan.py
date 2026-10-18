"""The system scanner completed its first pass."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class FSSDiscoveryScan(BaseEvent):
    name = "FSSDiscoveryScan"
    priority = LOW
    keep = ("BodyCount", "NonBodyCount",)
    summary = "System scan: {BodyCount} bodies"
