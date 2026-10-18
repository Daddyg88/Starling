"""Worked out from Status.json when heat goes over 100%. SAFETY: always announced."""

from events.base_event import BaseEvent
from core.event_bus import CRITICAL


class Overheating(BaseEvent):
    name = "Overheating"
    priority = CRITICAL
    source = "status"
    summary = "Ship is overheating"
