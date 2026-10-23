"""The main tank is down to half."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class FuelHalf(BaseEvent):
    """Made up by STARLING from Status.json: a gentle first nudge to start looking for fuel."""
    name = "FuelHalf"
    priority = NORMAL
    source = "status"
    summary = "Fuel is at half"
