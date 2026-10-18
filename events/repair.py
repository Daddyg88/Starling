"""You paid for a specific repair (hull, a module, or the paintwork)."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class Repair(BaseEvent):
    name = "Repair"
    priority = LOW
    keep = ("Item", "Cost",)
    summary = "Repaired {Item}"
