"""You are being pulled out of supercruise. SAFETY: always announced."""

from events.base_event import BaseEvent
from core.event_bus import CRITICAL


class Interdicted(BaseEvent):
    name = "Interdicted"
    priority = CRITICAL
    keep = ("Submitted", "Interdictor", "IsPlayer", "Faction",)
    summary = "Interdicted"

    def describe(self, data):
        who = data.get("Interdictor")
        if data.get("Submitted"):
            return "Submitted to interdiction" + (" by %s" % who if who else "")
        return "Interdicted" + (" by %s" % who if who else "") + "!"
