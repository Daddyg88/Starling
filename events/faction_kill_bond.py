"""You earned a combat bond."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class FactionKillBond(BaseEvent):
    name = "FactionKillBond"
    priority = NORMAL
    tag_on_foot = True
    keep = ("Reward", "VictimFaction",)
    summary = "Combat bond: {Reward:,} credits"
