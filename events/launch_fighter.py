"""You launched a fighter."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class LaunchFighter(BaseEvent):
    name = "LaunchFighter"
    priority = NORMAL
    keep = ("PlayerControlled",)
    summary = "Fighter launched"
