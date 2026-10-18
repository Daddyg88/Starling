"""You asked for docking permission."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class DockingRequested(BaseEvent):
    name = "DockingRequested"
    priority = LOW
    keep = ("StationName",)
    summary = "Docking requested at {StationName}"
