"""You pressed Play and loaded into the game."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class LoadGame(BaseEvent):
    name = "LoadGame"
    priority = LOW
    keep = ("Commander", "Ship", "Ship_Localised", "ShipName", "FuelLevel", "FuelCapacity",)
    summary = "Game loaded. Flying the {Ship_Localised}"

    def update_state(self, entry, state):
        state.game_quit = False
        state.commander = entry.get("Commander", state.commander)
        state.ship = entry.get("Ship_Localised") or entry.get("Ship") or state.ship
        state.ship_name = entry.get("ShipName") or state.ship_name
        state.ship_model = entry.get("Ship_Localised") or state.ship_model
        capacity = entry.get("FuelCapacity")
        if isinstance(capacity, (int, float)):
            state.fuel_capacity = capacity
