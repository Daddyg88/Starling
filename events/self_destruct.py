"""Self-destruct was started. SAFETY: always announced."""

from events.base_event import BaseEvent
from core.event_bus import CRITICAL


class SelfDestruct(BaseEvent):
    name = "SelfDestruct"
    priority = CRITICAL
    summary = "Self-destruct sequence started"
