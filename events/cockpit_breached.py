"""Your canopy is broken. SAFETY: always announced."""

from events.base_event import BaseEvent
from core.event_bus import CRITICAL


class CockpitBreached(BaseEvent):
    name = "CockpitBreached"
    priority = CRITICAL
    summary = "Cockpit breached"
