"""Fuel was scooped from a star."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class FuelScoop(BaseEvent):
    name = "FuelScoop"
    priority = LOW
    keep = ("Scooped", "Total",)
    summary = "Scooped {Scooped:.1f} t of fuel (tank now {Total:.1f} t)"
