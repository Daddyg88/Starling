"""You launched the SRV."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class LaunchSRV(BaseEvent):
    name = "LaunchSRV"
    priority = LOW
    summary = "SRV launched"

    def update_state(self, entry, state):
        state.in_nomad = False   # a normal SRV, not the Nomad
