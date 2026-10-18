"""You dropped out of supercruise at a signal source."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class SupercruiseDestinationDrop(BaseEvent):
    name = "SupercruiseDestinationDrop"
    priority = LOW
    keep = ("Type", "Threat",)
    summary = "Dropped into {Type}"
