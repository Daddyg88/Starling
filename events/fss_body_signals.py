"""Found with the system scanner (FSS): which signals a body has."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL
from events._signals import count_signals, describe_counts


class FSSBodySignals(BaseEvent):
    name = "FSSBodySignals"
    priority = NORMAL

    def handle(self, entry):
        data = {"BodyName": entry.get("BodyName")}
        data.update(count_signals(entry.get("Signals")))
        return data

    def describe(self, data):
        counts = {k: data.get(k, 0) for k in ("Biological", "Geological", "Human", "Guardian", "Thargoid", "Other")}
        return describe_counts(data.get("BodyName"), counts)
