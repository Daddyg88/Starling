"""The small fuel reservoir was refilled."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class ReservoirReplenished(BaseEvent):
    name = "ReservoirReplenished"
    priority = LOW
    keep = ("FuelMain", "FuelReservoir",)
    summary = "Fuel reservoir refilled ({FuelMain:.1f} t in tank)"
