"""A station gave you a landing pad."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class DockingGranted(BaseEvent):
    name = "DockingGranted"
    priority = NORMAL
    keep = ("StationName", "LandingPad",)
    summary = "Docking granted at {StationName}, pad {LandingPad}"
