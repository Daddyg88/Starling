"""
Shopping: buying a new ship or a new module. She loves shopping, especially with your money.
Their words live in voicepacks/default/shopping.json.
"""

from core.event_bus import NORMAL, LOW
from events.base_event import BaseEvent
from events.shipyard_swap import nice_ship_name


class ShipyardBuy(BaseEvent):
    """You bought a new ship."""
    name = "ShipyardBuy"
    priority = NORMAL
    keep = ("ShipType", "ShipType_Localised", "ShipPrice",)
    summary = "Bought a new {ship}"

    def handle(self, entry):
        data = super().handle(entry)
        data["ship"] = nice_ship_name(entry) or "ship"
        price = entry.get("ShipPrice")
        data["Price"] = "{:,}".format(int(price)) if isinstance(price, (int, float)) else ""
        return data


class ModuleBuy(BaseEvent):
    """You bought a ship module."""
    name = "ModuleBuy"
    priority = LOW
    keep = ("Slot", "BuyPrice",)
    summary = "Bought {module}"

    def handle(self, entry):
        data = super().handle(entry)
        raw = entry.get("BuyItem_Localised") or entry.get("BuyItem") or "a module"
        data["module"] = str(raw).replace("_", " ").strip()
        return data


class BuyDrones(BaseEvent):
    """You bought limpets."""
    name = "BuyDrones"
    priority = LOW
    keep = ("Type", "Count", "TotalCost",)
    summary = "Bought {Count} limpets"
