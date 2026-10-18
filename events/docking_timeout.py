"""Your docking permission ran out."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class DockingTimeout(BaseEvent):
    name = "DockingTimeout"
    priority = NORMAL
    keep = ("StationName",)
    summary = "Docking request timed out"
