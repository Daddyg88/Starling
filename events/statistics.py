"""
The game's Statistics event (written each time you load in). Nothing is said for the line itself.
journal/milestones.py watches it for round numbers (hours played, jumps, first footfalls, biological species) and she
cheers with GameMilestone; the species count is also kept for the exobiology progress line.
"""

from core.event_bus import NORMAL
from events.base_event import BaseEvent


class Statistics(BaseEvent):
    name = "Statistics"
    keep = ()

    def update_state(self, entry, state):
        for kind, value in state.milestones.check(entry):
            state.pending_events.append(("GameMilestone", {"Kind": kind, "Value": value, "Number": "{:,}".format(value)}))

    def handle(self, entry):
        data = super().handle(entry)
        data["_silent"] = True                      # nothing is said for the line itself, only for the milestones it made
        return data


class GameMilestone(BaseEvent):
    name = "GameMilestone"
    priority = NORMAL
    source = "status"
    summary = "{Kind}: {Number}"
