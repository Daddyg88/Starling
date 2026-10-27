"""Found with the system scanner (FSS): which signals a body has."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL
from events._signals import count_signals, describe_counts, ring_once


class FSSBodySignals(BaseEvent):
    name = "FSSBodySignals"
    priority = NORMAL

    def update_state(self, entry, state):
        """A body with life: she guesses what is on it (journal/bio_predict.py) and says so instead of the plain line."""
        self._guessed = False
        self._ring, self._ring_repeat = ring_once(entry, state)
        body, events = state.bio.note_fss(entry, state.system or "")
        if events:
            state.pending_events.extend(events)
        if body is not None and (events or body.awaiting) and state.bio._on("exobiology.guess", True):
            self._guessed = True

    def handle(self, entry):
        data = {"BodyName": entry.get("BodyName")}
        data.update(count_signals(entry.get("Signals")))
        if getattr(self, "_guessed", False):
            data["_silent"] = True          # the guess line already says there is life there
        if getattr(self, "_ring", None):
            data.update(self._ring)
            if getattr(self, "_ring_repeat", False):
                data["_silent"] = True
        return data

    def describe(self, data):
        if data.get("Summary"):
            return "Ring %s: %s %s: %s" % (data.get("BodyName"), data.get("Total"), data.get("Word"), data.get("Summary"))
        counts = {k: data.get(k, 0) for k in ("Biological", "Geological", "Human", "Guardian", "Thargoid", "Other")}
        return describe_counts(data.get("BodyName"), counts)
