"""A fighter returned to the ship."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class DockFighter(BaseEvent):
    name = "DockFighter"
    priority = LOW
    summary = "Fighter docked"
