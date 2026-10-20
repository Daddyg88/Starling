"""You swapped to another ship. She says which one."""

from core.ships import ship_name
from events.base_event import BaseEvent
from core.event_bus import NORMAL


def nice_ship_name(entry):
    """'python' -> 'Python', 'Type9' stays as the game's own spelling when it gives one."""
    return ship_name(entry.get("ShipType"), entry.get("ShipType_Localised"))


class ShipyardSwap(BaseEvent):
    name = "ShipyardSwap"
    priority = NORMAL
    keep = ("ShipType", "ShipType_Localised",)
    summary = "Switched ship to {ship}"

    def update_state(self, entry, state):
        state.ship = entry.get("ShipType") or state.ship
        state.ship_name = None                      # the Loadout that follows tells us the new ship's own name

    def handle(self, entry):
        data = super().handle(entry)
        data["ship"] = nice_ship_name(entry) or "another ship"
        return data
