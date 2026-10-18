"""
Fighting events: wings, other pilots, interdictions, suit loadouts.
Their words live in voicepacks/default/combat.json. Several small events share this one file.
"""

from core.event_bus import NORMAL
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


def _handle_target(self, entry):
    stage = entry.get("ScanStage") or 0
    return {"ScanStage": stage, "LegalStatus": entry.get("LegalStatus") or "", "Bounty": entry.get("Bounty") or 0,
            "Ship": entry.get("Ship_Localised") or entry.get("Ship") or "",
            "Pilot": entry.get("PilotName_Localised") or ""}


EVENT_CLASSES = [
    _make("WingInvite", "Someone invited you to a wing.", summary="{Name} invited you to a wing", extra={"handle": _handle_invite}),
    _make("WingAdd", "Someone joined your wing.", summary="{Name} joined the wing", extra={"handle": _handle_add}),
    _make("PVPKill", "You destroyed another commander.", summary="Destroyed {Victim}", on_foot=True, extra={"handle": _handle_pvp}),
    _make("Interdiction", "You tried to pull a ship out of supercruise.", summary="Interdiction", extra={"handle": _handle_interdiction}),
    _make("ShipTargeted", "You locked a ship (spoken only for wanted targets).", summary="Target locked", extra={"handle": _handle_target}),
    _make("CapShipBond", "A combat bond from a capital ship fight.", keep=("Reward", "VictimFaction"),
          summary="Capital ship bond: {Reward:,} credits", on_foot=True),
    _make("SwitchSuitLoadout", "You switched your suit loadout.", keep=("LoadoutName", "SuitName_Localised"),
          summary="Suit loadout: {LoadoutName}"),
]
