"""A mission failed. SAFETY: always announced."""

from events.base_event import BaseEvent
from core.event_bus import CRITICAL


class MissionFailed(BaseEvent):
    name = "MissionFailed"
    priority = CRITICAL
    keep = ("LocalisedName", "Name", "Fine",)
    summary = "Mission failed: {LocalisedName}"
