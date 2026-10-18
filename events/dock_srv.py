"""You recovered the SRV."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class DockSRV(BaseEvent):
    name = "DockSRV"
    priority = LOW
    keep = ("SRVType_Localised",)
    summary = "{SRVType_Localised} docked"
