"""The reboot and repair function was used."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class RebootRepair(BaseEvent):
    name = "RebootRepair"
    priority = NORMAL
    summary = "Rebooting and repairing systems"
