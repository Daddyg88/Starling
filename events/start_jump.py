"""Your jump drive has started charging."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class StartJump(BaseEvent):
    name = "StartJump"
    priority = NORMAL
    keep = ("JumpType", "StarSystem", "StarClass",)
    summary = "Charging {JumpType} jump"
