"""You stepped out of the Nomad and are on foot."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class NomadLeft(BaseEvent):
    """Made up by STARLING herself (not a journal line): it is announced through processor.emit()."""
    name = "NomadLeft"
    priority = LOW
    source = "status"
    summary = "You left the Nomad on foot"
