"""You found a codex entry."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class CodexEntry(BaseEvent):
    name = "CodexEntry"
    priority = LOW
    keep = ("Name_Localised", "Category_Localised", "IsNewEntry",)
    summary = "Codex entry: {Name_Localised}"
