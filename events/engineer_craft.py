"""An engineer upgraded a module."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class EngineerCraft(BaseEvent):
    name = "EngineerCraft"
    priority = LOW
    keep = ("Engineer", "BlueprintName", "Level",)
    summary = "Engineer upgrade: {BlueprintName} grade {Level}"
