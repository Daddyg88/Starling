"""You sold exploration data."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class SellExplorationData(BaseEvent):
    name = "SellExplorationData"
    priority = NORMAL
    keep = ("TotalEarnings",)
    summary = "Sold exploration data for {TotalEarnings:,} credits"
