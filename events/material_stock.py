"""Lines in the journal that change how many materials you hold (not announced; they only keep the count right)."""

from events.base_event import BaseEvent
from core.event_bus import LOW
from journal import materials


class Materials(BaseEvent):
    """Written when the game starts: everything you hold."""
    name = "Materials"
    priority = LOW
    announce = False

    def update_state(self, entry, state):
        materials.load_all(state, entry)


class MaterialDiscarded(BaseEvent):
    name = "MaterialDiscarded"
    priority = LOW
    announce = False

    def update_state(self, entry, state):
        materials.add(state, entry.get("Name"), -int(entry.get("Count", 0) or 0))


class ScientificResearch(BaseEvent):
    """Data handed in at a research terminal."""
    name = "ScientificResearch"
    priority = LOW
    announce = False

    def update_state(self, entry, state):
        materials.add(state, entry.get("Name"), -int(entry.get("Count", 0) or 0))


class MaterialTrade(BaseEvent):
    name = "MaterialTrade"
    priority = LOW
    announce = False

    def update_state(self, entry, state):
        paid, got = entry.get("Paid") or {}, entry.get("Received") or {}
        if isinstance(paid, dict) and paid.get("Material"):
            materials.add(state, paid["Material"], -int(paid.get("Quantity", 0) or 0))
        if isinstance(got, dict) and got.get("Material"):
            materials.add(state, got["Material"], int(got.get("Quantity", 0) or 0))


class TechnologyBroker(BaseEvent):
    name = "TechnologyBroker"
    priority = LOW
    announce = False

    def update_state(self, entry, state):
        materials.spend(state, entry.get("Materials"))
