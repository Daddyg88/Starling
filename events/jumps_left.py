"""How many jumps are left in your route."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class JumpsLeft(BaseEvent):
    """Made up by STARLING herself (not a journal line): it is announced through processor.emit()."""
    name = "JumpsLeft"
    priority = LOW
    source = "status"
    summary = "{jumps} jumps left in the route"
