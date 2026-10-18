"""You paid off bounties. (Only used for Starling's mood.)"""

from events.base_event import BaseEvent
from core.event_bus import LOW


class PayBounties(BaseEvent):
    name = "PayBounties"
    priority = LOW
    keep = ("Amount", "Faction",)
    summary = "Paid bounties: {Amount:,} credits"

    def update_state(self, entry, state):
        state.wanted = False
