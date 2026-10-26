"""
Notable Stellar Phenomena (NSP): Lagrange clouds and the molluscs, pods, crystals and spheres living in them.

  * A CodexEntry whose name is an NSP type (config/nsp.json) becomes NSPNew (first time in your codex) or NSPSeen, each with a small fact.
  * A system scanner (FSS) signal that is an NSP becomes NSPInSystem, once per system.
Her words are in voicepacks/default/nsp.json. The three events are made up by STARLING (pending events), like HighGradeHint.
"""

import json
import re

from core import paths
from core.event_bus import NORMAL
from core.logger import get_logger
from events.base_event import BaseEvent

log = get_logger("nsp")
_types = None


def types():
    global _types
    if _types is None:
        try:
            with open(paths.CONFIG_DIR / "nsp.json", "r", encoding="utf-8") as handle:
                _types = json.load(handle).get("types", [])
        except (OSError, ValueError):
            log.exception("Could not read config/nsp.json")
            _types = []
    return _types


def classify(name):
    """The NSP type for a codex entry name ('Albulum Bell Mollusc'), or None."""
    words = set(re.findall(r"[a-z]+", str(name or "").lower()))
    for item in types():
        if all(w in words for w in item["match"]):
            return item
    return None


def is_nsp_signal(entry):
    """True for an FSS signal that is a notable stellar phenomenon (journal name like $Fixed_Event_Life_Cloud;)."""
    for key in ("SignalName", "SignalName_Localised"):
        text = re.sub(r"[^a-z]", "", str(entry.get(key, "")).lower())
        if "stellarphenomen" in text or "fixedeventlife" in text or "lagrange" in text:
            return True
    return False


def note_codex(entry, state):
    """Called for every CodexEntry line. Returns True when it was an NSP (the plain codex line is then not spoken)."""
    item = classify(entry.get("Name_Localised") or entry.get("Name"))
    if item is None:
        return False
    name = str(entry.get("Name_Localised") or item["name"]).strip()
    new = bool(entry.get("IsNewEntry"))
    seen = state.nsp_seen
    if not new and name.casefold() in seen:
        return True                                      # you already heard about this one today
    seen.add(name.casefold())
    state.pending_events.append(("NSPNew" if new else "NSPSeen", {"Name": name, "Fact": item["fact"], "Kind": item["key"]}))
    return True


def note_signal(entry, state):
    if not is_nsp_signal(entry):
        return
    system = entry.get("SystemAddress") or state.system
    if state.nsp_system == system:
        return
    state.nsp_system = system
    state.pending_events.append(("NSPInSystem", {"System": state.system or ""}))


class NSPNew(BaseEvent):
    """A notable stellar phenomenon you had never scanned before."""
    name = "NSPNew"
    priority = NORMAL
    source = "status"
    summary = "New codex entry: {Name}"


class NSPSeen(BaseEvent):
    """A notable stellar phenomenon you have scanned before."""
    name = "NSPSeen"
    priority = NORMAL
    source = "status"
    summary = "Scanned {Name}"


class NSPInSystem(BaseEvent):
    """The system scanner found a notable stellar phenomenon in this system."""
    name = "NSPInSystem"
    priority = NORMAL
    source = "status"
    summary = "Notable stellar phenomenon in {System}"
