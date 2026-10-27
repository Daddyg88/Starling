"""After mapping a planet's surface: which signals (biological, geological...) it has."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL
from events._signals import count_signals, describe_counts, ring_once


class SAASignalsFound(BaseEvent):
    name = "SAASignalsFound"
    priority = NORMAL

    def update_state(self, entry, state):
        self._refined = False
        self._ring, self._ring_repeat = ring_once(entry, state)      # a ring she has mapped: how many hotspots, said once
        events = state.bio.note_saa(entry, state.system or "")
        if events:
            self._refined = True
            state.pending_events.extend(events)

    def handle(self, entry):
        data = {"BodyName": entry.get("BodyName")}
        data.update(count_signals(entry.get("Signals")))
        if getattr(self, "_refined", False):
            data["_silent"] = True          # the corrected guess says it better
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
