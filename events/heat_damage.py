"""Heat is damaging your ship. SAFETY: always announced."""

from events.base_event import BaseEvent
from core.event_bus import CRITICAL


class HeatDamage(BaseEvent):
    name = "HeatDamage"
    priority = CRITICAL
    summary = "Taking heat damage"
