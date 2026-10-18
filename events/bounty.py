"""You destroyed a wanted ship."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class Bounty(BaseEvent):
    name = "Bounty"
    priority = NORMAL
    keep = ("TotalReward", "VictimFaction", "Target",)
    summary = "Bounty claimed: {TotalReward:,} credits"
