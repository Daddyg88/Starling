"""You found a codex entry."""

from events.base_event import BaseEvent
from core.event_bus import LOW
from events.nsp import note_codex


class CodexEntry(BaseEvent):
    name = "CodexEntry"
    priority = LOW
    keep = ("Name_Localised", "Category_Localised", "IsNewEntry",)
    summary = "Codex entry: {Name_Localised}"

    def update_state(self, entry, state):
        self._nsp = note_codex(entry, state)
        state.bio.note_codex(entry)

    def handle(self, entry):
        data = super().handle(entry)
        if getattr(self, "_nsp", False):
            data["_silent"] = True                        # the notable stellar phenomenon lines replace "interesting"
        return data
