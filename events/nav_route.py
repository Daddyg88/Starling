"""You plotted a route in the galaxy map."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class NavRoute(BaseEvent):
    name = "NavRoute"
    priority = NORMAL
    summary = "Route plotted"
