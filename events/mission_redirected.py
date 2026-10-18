"""A mission got a new destination."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class MissionRedirected(BaseEvent):
    name = "MissionRedirected"
    priority = NORMAL
    keep = ("LocalisedName", "NewDestinationSystem",)
    summary = "Mission updated: {LocalisedName}"
