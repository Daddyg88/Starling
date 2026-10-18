"""Exobiology: you sold your biological data."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL
from journal.exobiology import spoken_credits


class SellOrganicData(BaseEvent):
    name = "SellOrganicData"
    priority = NORMAL

    def update_state(self, entry, state):
        state.exobiology.on_sell(entry)     # learns the real prices and empties what you carry

    def handle(self, entry):
        items = [i for i in (entry.get("BioData") or []) if isinstance(i, dict)]
        total = 0
        for item in items:
            for field in ("Value", "Bonus"):
                value = item.get(field, 0)
                total += value if isinstance(value, (int, float)) else 0
        return {"Count": len(items), "TotalValue": int(total), "worth": spoken_credits(total)}

    def describe(self, data):
        return "Sold %s organic samples for %s credits" % (data.get("Count", 0), format(data.get("TotalValue", 0), ","))
