"""
The template every event file is built from.

Fields you can set in an event file:
    name      the journal's event name, e.g. "FuelScoop"
    priority  CRITICAL, NORMAL or LOW (events.json can adjust it, except CRITICAL)
    source    "journal" (normal) or "status" (worked out from Status.json)
    announce  False = only update STARLING's knowledge, say nothing
    keep      which journal fields to keep
    summary   a sentence with {Field} gaps, e.g. "Scooped {Scooped:.1f} t of fuel"
"""

from core.event_bus import NORMAL


class _SafeDict(dict):
    def __missing__(self, key):
        return "?"


class BaseEvent:
    name = ""
    priority = NORMAL
    source = "journal"
    announce = True
    keep = ()
    summary = ""

    def handle(self, entry):
        """Pick out the useful fields from the raw journal entry."""
        return {key: entry[key] for key in self.keep if key in entry}

    def update_state(self, entry, state):
        """Update what STARLING knows about the game (ship, system, hull...)."""

    def describe(self, data):
        """A short sentence about this event."""
        if not self.summary:
            return self.name
        try:
            return self.summary.format_map(_SafeDict(data))
        except (ValueError, TypeError, KeyError):
            return self.name
