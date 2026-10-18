"""The game is closing."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class Shutdown(BaseEvent):
    name = "Shutdown"
    priority = NORMAL
    summary = "Game shutting down"
