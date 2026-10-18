"""Your refinery produced something."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class MiningRefined(BaseEvent):
    name = "MiningRefined"
    priority = LOW
    keep = ("Type",)
    summary = "Refined {Type}"
