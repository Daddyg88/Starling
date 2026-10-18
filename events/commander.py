"""Sent when the game starts and tells us your commander name."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class Commander(BaseEvent):
    name = "Commander"
    priority = LOW
    keep = ("Name",)
    summary = "Commander {Name} is on the bridge"

    def update_state(self, entry, state):
        state.commander = entry.get("Name")
