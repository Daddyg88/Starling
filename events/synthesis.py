"""You synthesised something."""

from events.base_event import BaseEvent
from core.event_bus import LOW
from journal import materials


class Synthesis(BaseEvent):
    name = "Synthesis"
    priority = LOW
    keep = ("Name",)
    summary = "Synthesised {Name}"

    def update_state(self, entry, state):
        materials.spend(state, entry.get("Materials"))
