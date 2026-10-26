"""A star or planet was scanned."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class Scan(BaseEvent):
    name = "Scan"
    priority = LOW
    keep = ("BodyName", "StarType", "PlanetClass", "TerraformState", "Landable", "WasDiscovered", "WasMapped", "WasFootfalled",)
    summary = "Scanned {BodyName}"

    def update_state(self, entry, state):
        state.exobiology.note_body(entry)
        state.pending_events.extend(state.bio.note_scan(entry))
        name, gravity, kelvin = entry.get("BodyName"), entry.get("SurfaceGravity"), entry.get("SurfaceTemperature")
        if name and isinstance(gravity, (int, float)) and isinstance(kelvin, (int, float)):
            if len(state.bodies) > 400:
                state.bodies.clear()          # a long trip must not grow this forever
            state.bodies[name] = {"temperature": float(kelvin), "gravity": float(gravity) / 9.80665}    # the game gives m/s2
        if state.awaiting_discovery:
            state.awaiting_discovery = False
            if entry.get("WasDiscovered") is False:
                state.pending_events.append(("UndiscoveredSystem", {"StarSystem": state.system or ""}))   # remembers whether anyone has stood on this body yet
