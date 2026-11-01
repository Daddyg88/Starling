"""You finished a mission."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class MissionCompleted(BaseEvent):
    name = "MissionCompleted"
    priority = NORMAL
    keep = ("LocalisedName", "Faction", "Reward", "MissionID",)
    summary = "Mission completed: {LocalisedName}"
