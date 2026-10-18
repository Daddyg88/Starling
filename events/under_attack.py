"""Someone is shooting at you. SAFETY: always announced."""

from events.base_event import BaseEvent
from core.event_bus import CRITICAL


class UnderAttack(BaseEvent):
    name = "UnderAttack"
    priority = CRITICAL
    tag_on_foot = True
    keep = ("Target",)
    summary = "Under attack (target: {Target})"
