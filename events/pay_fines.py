"""You paid off fines. (Only used for Starling's mood.)"""

from events.base_event import BaseEvent
from core.event_bus import LOW


class PayFines(BaseEvent):
    name = "PayFines"
    priority = LOW
    keep = ("Amount", "AllFines",)
    summary = "Paid fines: {Amount:,} credits"

    def update_state(self, entry, state):
        state.wanted = False
