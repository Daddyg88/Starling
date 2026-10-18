"""Another ship scanned you."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class Scanned(BaseEvent):
    name = "Scanned"
    priority = NORMAL
    keep = ("ScanType",)
    summary = "Your ship was scanned ({ScanType})"
