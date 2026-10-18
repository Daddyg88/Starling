"""You took a mission."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class MissionAccepted(BaseEvent):
    name = "MissionAccepted"
    priority = NORMAL
    keep = ("LocalisedName", "Faction", "Expiry", "Reward", "MissionID",)
    summary = "Mission accepted: {LocalisedName}"
