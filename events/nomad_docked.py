"""The Nomad was recovered."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class NomadDocked(BaseEvent):
    """Made up by STARLING herself (not a journal line): it is announced through processor.emit()."""
    name = "NomadDocked"
    priority = LOW
    source = "status"
    summary = "The Nomad is back aboard"
