"""The system scanner found a signal source."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class FSSSignalDiscovered(BaseEvent):
    name = "FSSSignalDiscovered"
    priority = LOW
    keep = ("SignalName",)
    summary = "Signal discovered: {SignalName}"
