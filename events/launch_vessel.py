"""You launched a ship-launched vessel (the Nomad). The game calls it a "vessel", not an SRV."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class LaunchVessel(BaseEvent):
    name = "LaunchVessel"
    priority = NORMAL
    keep = ("VesselType", "VesselType_Localised", "PlayerControlled")
    summary = "{VesselType_Localised} launched"

    def update_state(self, entry, state):
        # Status.json reports the Nomad as an SRV, so remember that this one is a Nomad.
        vessel = str(entry.get("VesselType_Localised") or entry.get("VesselType") or "").lower()
        state.in_nomad = vessel in ("nomad", "lander01")
