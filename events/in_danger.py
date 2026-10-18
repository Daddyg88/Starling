"""Worked out from Status.json when the game flags danger. SAFETY: always announced."""

from events.base_event import BaseEvent
from core.event_bus import CRITICAL


class InDanger(BaseEvent):
    name = "InDanger"
    priority = CRITICAL
    source = "status"
    summary = "Ship is in danger"
