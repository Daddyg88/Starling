"""You landed on a planet."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class Touchdown(BaseEvent):
    name = "Touchdown"
    priority = NORMAL
    keep = ("PlayerControlled", "Latitude", "Longitude",)
    summary = "Touched down on the surface"
