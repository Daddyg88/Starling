"""You bought something at a market."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class MarketBuy(BaseEvent):
    name = "MarketBuy"
    priority = LOW
    keep = ("Type", "Count", "BuyPrice", "TotalCost", "IllegalGoods", "BlackMarket",)
    summary = "Bought {Count} {Type}"
