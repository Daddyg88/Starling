"""You picked up an engineering material."""

from events.base_event import BaseEvent
from core.event_bus import LOW
from journal import materials


class MaterialCollected(BaseEvent):
    name = "MaterialCollected"
    priority = LOW
    keep = ("Category", "Name", "Count",)
    summary = "Collected {Count} {Name}"

    def update_state(self, entry, state):
        materials.add(state, entry.get("Name"), entry.get("Count", 1))
