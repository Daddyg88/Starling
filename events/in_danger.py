"""Worked out from Status.json when the game flags danger. OFF by default (0.92.8): the game raises this flag at odd moments and Benny
knows when he is in danger; the dedicated warnings (UnderAttack, shields, hull, heat, fuel) are still always on."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class InDanger(BaseEvent):
    name = "InDanger"
    priority = NORMAL
    source = "status"
    summary = "Ship is in danger"
