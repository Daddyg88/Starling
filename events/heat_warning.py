"""Your ship is getting too hot. SAFETY: always announced."""

from events.base_event import BaseEvent
from core.event_bus import CRITICAL


class HeatWarning(BaseEvent):
    name = "HeatWarning"
    priority = CRITICAL
    summary = "Heat warning"
