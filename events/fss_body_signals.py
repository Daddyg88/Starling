"""Found with the system scanner (FSS): which signals a body has."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL
from events._signals import count_signals, describe_counts


class FSSBodySignals(BaseEvent):
    name = "FSSBodySignals"
    priority = NORMAL

    def update_state(self, entry, state):
        """A body with life: she guesses what is on it (journal/bio_predict.py) and says so instead of the plain line."""
        self._guessed = False
        body, events = state.bio.note_fss(entry, state.system or "")
        if events:
            self._guessed = True
            state.pending_events.extend(events)

    def handle(self, entry):
        data = {"BodyName": entry.get("BodyName")}
        data.update(count_signals(entry.get("Signals")))
        if getattr(self, "_guessed", False):
            data["_silent"] = True          # the guess line already says there is life there
        return data

    def describe(self, data):
        counts = {k: data.get(k, 0) for k in ("Biological", "Geological", "Human", "Guardian", "Thargoid", "Other")}
        return describe_counts(data.get("BodyName"), counts)
