"""You selected the next jump target."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class FSDTarget(BaseEvent):
    name = "FSDTarget"
    priority = LOW
    keep = ("Name", "RemainingJumpsInRoute",)
    summary = "Next jump target: {Name}"
