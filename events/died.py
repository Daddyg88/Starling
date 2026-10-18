"""Your ship was destroyed. SAFETY: always announced."""

from events.base_event import BaseEvent
from core.event_bus import CRITICAL


class Died(BaseEvent):
    name = "Died"
    priority = CRITICAL
    keep = ("KillerName", "KillerShip", "KillerRank",)

    def describe(self, data):
        killer = data.get("KillerName")
        return "Ship destroyed by %s" % killer if killer else "Ship destroyed"

    def update_state(self, entry, state):
        state.exobiology.on_death(entry)    # unsold exobiology data is lost when you die
