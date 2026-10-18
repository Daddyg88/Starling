"""Your fighter was destroyed."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class FighterDestroyed(BaseEvent):
    name = "FighterDestroyed"
    priority = NORMAL
    summary = "Fighter destroyed"
