"""
Fighting events: wings, other pilots, interdictions, suit loadouts.
Their words live in voicepacks/default/combat.json. Several small events share this one file.
"""

import re
import time

from core.event_bus import NORMAL
from core.ships import ship_name
from events.base_event import BaseEvent


def _make(name, doc, keep=(), summary="", on_foot=False, extra=None):
    attrs = {"__module__": __name__, "__doc__": doc, "name": name, "priority": NORMAL,
             "keep": tuple(keep), "summary": summary, "tag_on_foot": on_foot}
    attrs.update(extra or {})
    return type(name, (BaseEvent,), attrs)


def _handle_invite(self, entry):
    return {"Name": entry.get("Name") or "someone"}


def _handle_add(self, entry):
    return {"Name": entry.get("Name") or "someone"}


def _handle_pvp(self, entry):
    return {"Victim": entry.get("Victim") or "a pilot"}


def _handle_interdiction(self, entry):
    return {"Success": bool(entry.get("Success")), "IsPlayer": bool(entry.get("IsPlayer")),
            "Interdicted": entry.get("Interdicted") or "", "Submitted": bool(entry.get("Submitted"))}


THARGOID_NAMES = ("scout", "cyclops", "basilisk", "medusa", "hydra", "orthrus", "glaive", "titan")


def _is_thargoid(entry):
    """A Thargoid ship (Anti-Xeno). The game calls them scout, cyclops, basilisk, medusa, hydra, orthrus..."""
    raw = str(entry.get("Ship") or "").lower().strip("$;")
    local = str(entry.get("Ship_Localised") or "").lower()
    if "thargoid" in raw or "thargoid" in local:
        return True
    return raw in THARGOID_NAMES or re.match(r"^scout(_|$)", raw) is not None or local in THARGOID_NAMES


LOST_SECONDS = 30            # a target that flickers off and back on within this time is still the same target
TOLD_AGAIN_SECONDS = 120     # the same pilot's bounty is not read out again within this time
_now = time.monotonic


def _same_target(seen, ship, pilot):
    """The game gives no pilot name at scan stage 0 and adds it at stage 1, so an empty name matches any name."""
    return seen is not None and seen[0] == ship and (not pilot or not seen[1] or pilot == seen[1])


def _target_update(self, entry, state):
    """Decide what (if anything) is worth saying about the ship you just targeted or scanned."""
    try:                                                    # what sub targeting needs to know (control/subsystems.py)
        lowered = {str(k).lower(): v for k, v in entry.items()}
        state.target_locked = bool(entry.get("TargetLocked", True))
        state.target_scan = int(entry.get("ScanStage") or 0)
        state.target_subsystem = str(lowered.get("subsystem") or "") if state.target_locked else ""
        state.target_subsystem_readable = str(lowered.get("subsystem_localised") or "") if state.target_locked else ""
        state.target_seq = getattr(state, "target_seq", 0) + 1
    except Exception:
        pass
    ship = entry.get("Ship_Localised") or entry.get("Ship") or ""
    pilot = entry.get("PilotName_Localised") or entry.get("PilotName") or ""
    now = _now()
    if not entry.get("TargetLocked", True) or not ship:
        self._lost_at = now                                             # keep what we know: it may flicker back on
        self._pending = ""
        return
    lost_at = getattr(self, "_lost_at", None)
    if self._seen is not None and lost_at is not None and now - lost_at > LOST_SECONDS:
        self._seen, self._bounty_told = None, None
    self._lost_at = None
    stage = entry.get("ScanStage") or 0
    pending = ""
    flags = getattr(state, "status_flags", None)
    fighting = bool(flags is not None and (flags >> 6) & 1)               # hardpoints out
    if not _same_target(self._seen, ship, pilot):
        self._seen, self._bounty_told = (ship, pilot), None
        if _is_thargoid(entry):
            pending = "thargoid"                                         # always worth a word, hardpoints or not
        elif fighting:
            pending = "ship"
    elif pilot and not self._seen[1]:
        self._seen = (ship, pilot)                                       # now we know who it is
    wanted = "wanted" in str(entry.get("LegalStatus", "")).lower()
    if stage >= 3 and not self._bounty_told and (wanted or entry.get("Bounty")) and pending != "thargoid":
        self._bounty_told = True
        told = self.__dict__.setdefault("_told_at", {})
        key = (ship, pilot)
        if not pilot or now - told.get(key, -1e9) >= TOLD_AGAIN_SECONDS:
            told[key] = now
            if len(told) > 60:
                for old in sorted(told, key=told.get)[:20]:
                    del told[old]
            pending = "bounty" if entry.get("Bounty") else "wanted"
    self._pending = pending


def _handle_target(self, entry):
    bounty = entry.get("Bounty") or 0
    return {"ScanStage": entry.get("ScanStage") or 0, "LegalStatus": entry.get("LegalStatus") or "", "Bounty": bounty,
            "BountyText": "{:,}".format(bounty) if isinstance(bounty, (int, float)) else str(bounty),
            "Ship": ship_name(entry.get("Ship"), entry.get("Ship_Localised")),
            "Pilot": entry.get("PilotName_Localised") or "", "Announce": getattr(self, "_pending", "")}


EVENT_CLASSES = [
    _make("WingInvite", "Someone invited you to a wing.", summary="{Name} invited you to a wing", extra={"handle": _handle_invite}),
    _make("WingAdd", "Someone joined your wing.", summary="{Name} joined the wing", extra={"handle": _handle_add}),
    _make("PVPKill", "You destroyed another commander.", summary="Destroyed {Victim}", on_foot=True, extra={"handle": _handle_pvp}),
    _make("Interdiction", "You tried to pull a ship out of supercruise.", summary="Interdiction", extra={"handle": _handle_interdiction}),
    _make("ShipTargeted", "You locked a ship (spoken only for wanted targets).", summary="Target locked", extra={"handle": _handle_target, "update_state": _target_update,
                                                                                                   "_seen": None, "_bounty_told": None, "_pending": ""}),
    _make("CapShipBond", "A combat bond from a capital ship fight.", keep=("Reward", "VictimFaction"),
          summary="Capital ship bond: {Reward:,} credits", on_foot=True),
    _make("SwitchSuitLoadout", "You switched your suit loadout.", keep=("LoadoutName", "SuitName_Localised"),
          summary="Suit loadout: {LoadoutName}"),
]
