"""Your hull took damage. SAFETY: always announced."""

from events.base_event import BaseEvent
from core.event_bus import CRITICAL


class HullDamage(BaseEvent):
    name = "HullDamage"
    priority = CRITICAL
    keep = ("Health", "PlayerPilot", "Fighter",)

    def handle(self, entry):
        data = super().handle(entry)
        data.setdefault("Fighter", False)
        data.setdefault("PlayerPilot", True)
        health = entry.get("Health")
        if isinstance(health, (int, float)):
            data["Percent"] = round(health * 100)
        return data

    def update_state(self, entry, state):
        health = entry.get("Health")
        if isinstance(health, (int, float)) and entry.get("PlayerPilot", True) \
                and not entry.get("Fighter", False):
            state.hull_health = health

    def describe(self, data):
        who = "Fighter hull" if data.get("Fighter") else "Hull integrity"
        return "%s at %s%%" % (who, data.get("Percent", "?"))
