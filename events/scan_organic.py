"""
Exobiology: you took a biological sample.

The game says Log (1st), Sample (2nd), Sample (3rd), then Analyse (finished).
journal/exobiology.py does the counting, so STARLING can say "third sample" correctly
and, once finished, what the species is worth and how much you are carrying.
"""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class ScanOrganic(BaseEvent):
    name = "ScanOrganic"
    priority = NORMAL
    keep = ("ScanType", "Genus_Localised", "Species_Localised", "Variant_Localised")

    def update_state(self, entry, state):
        # Stash the extra facts on the entry so handle() can pass them on.
        entry["_exo"] = state.exobiology.on_scan_organic(entry)

    def handle(self, entry):
        data = super().handle(entry)
        data.update(entry.get("_exo") or {})
        return data

    def describe(self, data):
        species = data.get("Species_Localised") or data.get("Genus_Localised")
        if data.get("Complete"):
            text = "Analysis complete"
        else:
            text = "Sample %s of 3" % data.get("SampleNumber", "?")
        if data.get("worth"):
            text += " (worth about %s credits" % data["worth"] + (", first footfall)" if data.get("FirstFootfall") else ")")
        return "%s: %s" % (text, species) if species else text
