"""You took off from a planet."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class Liftoff(BaseEvent):
    name = "Liftoff"
    priority = NORMAL
    keep = ("PlayerControlled",)
    summary = "Lifted off"
