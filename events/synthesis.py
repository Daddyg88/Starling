"""You synthesised something."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class Synthesis(BaseEvent):
    name = "Synthesis"
    priority = LOW
    keep = ("Name",)
    summary = "Synthesised {Name}"
