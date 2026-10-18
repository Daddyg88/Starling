"""You repaired your ship at a station."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class RepairAll(BaseEvent):
    name = "RepairAll"
    priority = LOW
    keep = ("Cost",)
    summary = "Ship repaired"
