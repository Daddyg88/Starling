"""A planet's surface has been mapped."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class SAAScanComplete(BaseEvent):
    name = "SAAScanComplete"
    priority = NORMAL
    keep = ("BodyName", "ProbesUsed", "EfficiencyTarget",)
    summary = "Surface scan complete on {BodyName}"
