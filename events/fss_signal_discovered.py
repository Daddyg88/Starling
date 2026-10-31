"""The system scanner found a signal source. A High Grade Emissions source gets its own callout (once per system)."""

import re

from events.base_event import BaseEvent
from events.nsp import is_nsp_signal, note_signal
from core.event_bus import LOW, NORMAL
from core.logger import get_logger

log = get_logger("fss_signal")


def is_high_grade(entry):
    """True when any name field of an FSS signal says High Grade Emissions ($USS_HighGradeEmissions;, 'High Grade Emissions')."""
    for key in ("SignalName", "SignalName_Localised", "USSType", "USSType_Localised"):
        text = re.sub(r"[^a-z]", "", str(entry.get(key, "")).lower())
        if "highgrade" in text:
            return True
    return False


class FSSSignalDiscovered(BaseEvent):
    name = "FSSSignalDiscovered"
    priority = LOW
    keep = ("SignalName",)
    summary = "Signal discovered: {SignalName}"

    def handle(self, entry):
        data = super().handle(entry)
        if is_high_grade(entry) or is_nsp_signal(entry):
            data["_silent"] = True                        # the High Grade Emissions callout replaces "signal detected"
        return data

    def update_state(self, entry, state):
        note_signal(entry, state)
        if not str(entry.get("SignalName", "")).lower().startswith(("$uss", "$fixed_event")) and not entry.get("USSType"):
            return
        seen = getattr(state, "_fss_logged", None)
        if seen is None:
            seen = state._fss_logged = set()
        key = (state.system, entry.get("SignalName"), entry.get("USSType"))
        (log.debug if key in seen else log.info)("FSS signal: %s / %s / %s", entry.get("SignalName"), entry.get("SignalName_Localised"), entry.get("USSType"))
        seen.add(key)                                      # the same kind of signal in the same system is logged once, not thirty times at start-up
        if not is_high_grade(entry):
            return
        system = entry.get("SystemAddress") or state.system
        if getattr(state, "hge_system", None) == system:
            return                                        # she already told you about this system
        state.hge_system = system
        state.pending_events = list(getattr(state, "pending_events", None) or []) + [("HighGradeEmissions", {"System": state.system or ""})]


class HighGradeEmissions(BaseEvent):
    """The system has a High Grade Emissions source (worth a look for materials). Her words: voicepacks/default/exploration2.json."""
    name = "HighGradeEmissions"
    priority = NORMAL
    keep = ("System",)
    summary = "High grade emissions in {System}"
