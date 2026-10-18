"""You cancelled a docking request."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class DockingCancelled(BaseEvent):
    name = "DockingCancelled"
    priority = LOW
    keep = ("StationName",)
    summary = "Docking request cancelled"
