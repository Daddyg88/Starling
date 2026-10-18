"""You left a station."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class Undocked(BaseEvent):
    name = "Undocked"
    priority = NORMAL
    keep = ("StationName",)
    summary = "Undocked from {StationName}"

    def update_state(self, entry, state):
        state.docked = False
        state.station = None
