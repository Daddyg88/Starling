"""A station refused docking."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class DockingDenied(BaseEvent):
    name = "DockingDenied"
    priority = NORMAL
    keep = ("StationName", "Reason",)
    summary = "Docking denied: {Reason}"
