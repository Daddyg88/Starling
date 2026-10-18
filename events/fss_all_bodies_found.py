"""Every body in the system has been found."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class FSSAllBodiesFound(BaseEvent):
    name = "FSSAllBodiesFound"
    priority = NORMAL
    keep = ("SystemName", "Count",)
    summary = "All {Count} bodies found in {SystemName}"
