"""Worked out from Status.json when fuel drops below 25%. SAFETY: always announced."""

from events.base_event import BaseEvent
from core.event_bus import CRITICAL


class LowFuel(BaseEvent):
    name = "LowFuel"
    priority = CRITICAL
    source = "status"
    keep = ("fuel_main", "fuel_percent",)

    def describe(self, data):
        main = data.get("fuel_main")
        percent = data.get("fuel_percent")
        if main is None:
            return "Fuel is low"
        if percent is not None:
            return "Fuel is low: %.1f t (%d%%)" % (main, percent)
        return "Fuel is low: %.1f t" % main
