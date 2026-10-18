"""You dumped cargo."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class EjectCargo(BaseEvent):
    name = "EjectCargo"
    priority = NORMAL
    keep = ("Type", "Count",)
    summary = "Ejected {Count} {Type}"
