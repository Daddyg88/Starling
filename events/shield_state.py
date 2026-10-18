"""Your shields went down or came back up. SAFETY: always announced."""

from events.base_event import BaseEvent
from core.event_bus import CRITICAL


class ShieldState(BaseEvent):
    name = "ShieldState"
    priority = CRITICAL
    keep = ("ShieldsUp",)

    def update_state(self, entry, state):
        if "ShieldsUp" in entry:
            state.shields_up = bool(entry["ShieldsUp"])

    def describe(self, data):
        return "Shields are back up" if data.get("ShieldsUp") else "Shields are DOWN"
