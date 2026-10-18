"""You gave up on a mission."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class MissionAbandoned(BaseEvent):
    name = "MissionAbandoned"
    priority = NORMAL
    keep = ("LocalisedName",)
    summary = "Mission abandoned: {LocalisedName}"
