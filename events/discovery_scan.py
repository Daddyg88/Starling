"""You used the discovery scanner (honk)."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class DiscoveryScan(BaseEvent):
    name = "DiscoveryScan"
    priority = LOW
    keep = ("Bodies",)
    summary = "Discovery scan found {Bodies} bodies"
