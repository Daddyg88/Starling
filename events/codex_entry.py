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
        self._green = "green_sudarsky" in str(entry.get("Name") or "").lower()
        if self._green:            # the game marks a green gas giant with its own codex entry, nothing in the Scan line says so
            state.pending_events.append(("GreenGasGiant", {"New": bool(entry.get("IsNewEntry")), "System": state.system or ""}))

    def handle(self, entry):
        data = super().handle(entry)
        if getattr(self, "_nsp", False) or getattr(self, "_green", False):
            data["_silent"] = True                        # the notable stellar phenomenon lines replace "interesting"
        return data
