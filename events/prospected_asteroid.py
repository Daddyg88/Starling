"""You prospected an asteroid."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class ProspectedAsteroid(BaseEvent):
    name = "ProspectedAsteroid"
    priority = LOW
    keep = ("Content_Localised",)
    summary = "Asteroid prospected: {Content_Localised}"
