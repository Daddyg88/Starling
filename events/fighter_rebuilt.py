"""Your fighter was rebuilt."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class FighterRebuilt(BaseEvent):
    name = "FighterRebuilt"
    priority = LOW
    summary = "Fighter rebuilt"
