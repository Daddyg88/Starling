"""You sold something at a market."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class MarketSell(BaseEvent):
    name = "MarketSell"
    priority = LOW
    keep = ("Type", "Count", "SellPrice", "TotalSale", "IllegalGoods", "StolenGoods", "BlackMarket",)
    summary = "Sold {Count} {Type}"
