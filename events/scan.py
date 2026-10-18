"""A star or planet was scanned."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class Scan(BaseEvent):
    name = "Scan"
    priority = LOW
    keep = ("BodyName", "StarType", "PlanetClass", "TerraformState", "Landable", "WasDiscovered", "WasMapped", "WasFootfalled",)
    summary = "Scanned {BodyName}"

    def update_state(self, entry, state):
        state.exobiology.note_body(entry)   # remembers whether anyone has stood on this body yet
