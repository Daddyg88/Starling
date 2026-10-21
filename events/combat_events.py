"""
Fighting events: wings, other pilots, interdictions, suit loadouts.
Their words live in voicepacks/default/combat.json. Several small events share this one file.
"""

import re

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


def _target_update(self, entry, state):
    """Decide what (if anything) is worth saying about the ship you just targeted or scanned."""
    ship = entry.get("Ship_Localised") or entry.get("Ship") or ""
    pilot = entry.get("PilotName_Localised") or entry.get("PilotName") or ""
    if not entry.get("TargetLocked", True) or not ship:
        self._seen, self._bounty_told, self._pending = None, None, ""
        return
    target = (ship, pilot)
    stage = entry.get("ScanStage") or 0
    pending = ""
    flags = getattr(state, "status_flags", None)
    fighting = bool(flags is not None and (flags >> 6) & 1)               # hardpoints out
    if target != self._seen:
        self._seen, self._bounty_told = target, None
        if _is_thargoid(entry):
            pending = "thargoid"                                         # always worth a word, hardpoints or not
        elif fighting:
            pending = "ship"
    wanted = "wanted" in str(entry.get("LegalStatus", "")).lower()
    if stage >= 3 and self._bounty_told != target and (wanted or entry.get("Bounty")) and pending != "thargoid":
        self._bounty_told = target
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
