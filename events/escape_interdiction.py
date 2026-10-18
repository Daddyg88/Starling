"""You got away from an interdiction."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class EscapeInterdiction(BaseEvent):
    name = "EscapeInterdiction"
    priority = NORMAL
    keep = ("Interdictor", "IsPlayer",)
    summary = "Escaped the interdiction"
