"""Your jump drive has started charging."""

from events.base_event import BaseEvent

SCOOPABLE = set("OBAFGKM")      # the fuel scoop only works on these star classes
from core.event_bus import NORMAL


class StartJump(BaseEvent):
    name = "StartJump"
    priority = NORMAL
    keep = ("JumpType", "StarSystem", "StarClass",)
    summary = "Charging {JumpType} jump"

    def handle(self, entry):
        data = super().handle(entry)
        star = str(entry.get("StarClass") or "").strip()
        if star:
            data["Scoopable"] = star[:1].upper() in SCOOPABLE and star.upper() not in ("N", "H")
            if star.upper() == "N":
                data["Boost"] = "neutron"           # not for fuel, but you can supercharge the drive there
            elif star[:1].upper() == "D":
                data["Boost"] = "whitedwarf"        # white dwarfs (D, DA, DB...) give a smaller supercharge
        return data

    def update_state(self, entry, state):
        if str(entry.get("JumpType") or "").lower() == "hyperspace":
            try:
                state.bio.start_leaving()          # the biology overlay goes now, not when you arrive
            except Exception:
                pass
