"""You picked up an engineering material."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class MaterialCollected(BaseEvent):
    name = "MaterialCollected"
    priority = LOW
    keep = ("Category", "Name", "Count",)
    summary = "Collected {Count} {Name}"
