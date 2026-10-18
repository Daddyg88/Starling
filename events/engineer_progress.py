"""Your standing with an engineer changed."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class EngineerProgress(BaseEvent):
    name = "EngineerProgress"
    priority = LOW
    keep = ("Engineer", "Progress", "Rank", "RankProgress",)
    summary = "Engineer progress: {Engineer}"
