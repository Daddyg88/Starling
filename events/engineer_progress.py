"""Your standing with an engineer changed."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class EngineerProgress(BaseEvent):
    name = "EngineerProgress"
    priority = LOW
    keep = ("Engineer", "Progress", "Rank", "RankProgress",)
    summary = "Engineer progress: {Engineer}"

    def update_state(self, entry, state):
        # When the game loads, the journal writes ONE EngineerProgress holding the whole list ("Engineers": [...]) and no
        # single "Engineer". That is not news, so she stays quiet. A real step with one engineer has the "Engineer" field.
        self.announce = "Engineer" in entry
