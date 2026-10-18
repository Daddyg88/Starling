"""A jet cone damaged one of your modules."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class JetConeDamage(BaseEvent):
    name = "JetConeDamage"
    priority = NORMAL
    keep = ("Module",)
    summary = "Jet cone damaged a module"
