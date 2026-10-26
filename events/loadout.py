"""Your ship's equipment. Not announced; used to learn your fuel tank size."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class Loadout(BaseEvent):
    name = "Loadout"
    priority = LOW
    announce = False

    def update_state(self, entry, state):
        state.ship = entry.get("Ship") or state.ship
        state.ship_name = entry.get("ShipName") or state.ship_name
        state.ship_model = entry.get("Ship_Localised") or state.ship_model
        capacity = entry.get("FuelCapacity")
        if isinstance(capacity, dict) and isinstance(capacity.get("Main"), (int, float)):
            state.fuel_capacity = capacity["Main"]
        mods = entry.get("Modules")
        if isinstance(mods, list):
            state.modules = [str(m.get("Item", "")) for m in mods if isinstance(m, dict)]
        cargo = entry.get("CargoCapacity")
        if isinstance(cargo, (int, float)):
            state.cargo_capacity = float(cargo)
        jump_range = entry.get("MaxJumpRange")
        if isinstance(jump_range, (int, float)) and jump_range > 0:
            state.max_jump_range = float(jump_range)
