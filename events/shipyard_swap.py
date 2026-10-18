"""You swapped to another ship."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class ShipyardSwap(BaseEvent):
    name = "ShipyardSwap"
    priority = NORMAL
    keep = ("ShipType",)
    summary = "Switched ship to {ShipType}"
