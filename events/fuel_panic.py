"""The main tank is nearly empty."""

from events.base_event import BaseEvent
from core.event_bus import CRITICAL


class FuelPanic(BaseEvent):
    """Made up by STARLING from Status.json: 10 percent left. A safety warning, so it cannot be switched off."""
    name = "FuelPanic"
    priority = CRITICAL
    source = "status"
    summary = "Fuel is almost gone"
