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
        return data
