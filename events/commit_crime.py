"""You committed a crime."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class CommitCrime(BaseEvent):
    name = "CommitCrime"
    priority = NORMAL
    keep = ("CrimeType", "Faction", "Fine", "Bounty",)
    summary = "Crime committed: {CrimeType}"

    def update_state(self, entry, state):
        bounty = entry.get("Bounty", 0)
        if isinstance(bounty, (int, float)) and bounty > 0:
            state.wanted = True          # you now have a bounty (notoriety)
