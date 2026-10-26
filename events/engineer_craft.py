"""An engineer upgraded a module."""

from events.base_event import BaseEvent
from core.event_bus import LOW
from journal import materials


class EngineerCraft(BaseEvent):
    name = "EngineerCraft"
    priority = LOW
    keep = ("Engineer", "BlueprintName", "Level",)
    summary = "Engineer upgrade: {BlueprintName} grade {Level}"

    def update_state(self, entry, state):
        materials.spend(state, entry.get("Ingredients"))
