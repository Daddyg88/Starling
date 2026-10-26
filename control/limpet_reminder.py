"""
Limpet reminder: when you dock, she reminds you to buy limpets, but ONLY if the ship you are flying right now has all three of:
  * a refinery        (item names like int_refinery_size2_class1)
  * a collector limpet controller   (int_dronecontrol_collection_size1_class1)
  * cargo racks       (int_cargorack_size5_class1, or the corrosion-proof kind)
The modules come from the Loadout event (the game writes one whenever you swap ships or change modules).
She stays quiet when: the setting is off, the station has no commodity market, or you already carry enough limpets (Cargo.json).
"""

import json
from pathlib import Path

from core.logger import get_logger

log = get_logger("limpets")

ENOUGH = 100              # carrying this many limpets or more = no reminder


def has_mining_kit(modules):
    """True when the module names include a refinery, a collector limpet controller and a cargo rack."""
    names = [str(m).lower() for m in (modules or [])]
    refinery = any("refinery" in n for n in names)
    collector = any("dronecontrol_collection" in n for n in names)
    racks = any("cargorack" in n for n in names)
    return refinery and collector and racks


def limpets_carried(folder):
    """Limpets in the hold according to Cargo.json, or None when it cannot be read."""
    if not folder:
        return None
    try:
        data = json.loads((Path(folder) / "Cargo.json").read_text(encoding="utf-8", errors="ignore"))
    except (OSError, ValueError):
        return None
    total = 0
    for item in data.get("Inventory") or []:
        try:
            if str(item.get("Name", "")).lower() == "drones":
                total += int(item.get("Count", 0))
        except (AttributeError, TypeError, ValueError):
            continue
    return total


class LimpetReminder:
    def __init__(self, bus, settings, narrator, state_provider, folder_provider):
        self.bus = bus
        self.settings = settings
        self.narrator = narrator
        self.state_provider = state_provider
        self.folder_provider = folder_provider

    def attach(self):
        self.bus.subscribe("Docked", self.on_docked)

    def detach(self):
        self.bus.unsubscribe("Docked", self.on_docked)

    def on_docked(self, event):
        try:
            if not self.settings.get("mining.limpet_reminder", True):
                return
            data = getattr(event, "data", None) or {}
            services = data.get("StationServices")
            if isinstance(services, (list, tuple)) and services and "commodities" not in services:
                return                                    # no market here, nothing to buy
            state = self.state_provider()
            if not has_mining_kit(getattr(state, "modules", None)):
                return
            carried = limpets_carried(self.folder_provider())
            if carried is not None and carried >= ENOUGH:
                return
            self.narrator.say("Mining_LimpetReminder", {"Count": carried if carried is not None else ""})
        except Exception:
            log.exception("The limpet reminder failed")
