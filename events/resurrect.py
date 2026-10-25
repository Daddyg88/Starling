"""You paid your rebuy after being destroyed."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class Resurrect(BaseEvent):
    name = "Resurrect"
    priority = NORMAL
    tag_on_foot = True
    keep = ("Option", "Cost", "Bankrupt",)
    summary = "Rebuy paid. Ship restored"
