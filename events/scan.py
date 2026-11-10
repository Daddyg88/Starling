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
        self._note_notable(entry, state)
        if state.awaiting_discovery:
            state.awaiting_discovery = False
            if entry.get("WasDiscovered") is False:
                state.pending_events.append(("UndiscoveredSystem", {"StarSystem": state.system or ""}))   # remembers whether anyone has stood on this body yet

    NOTABLE_CLASSES = {"Earthlike body": "earth-like world", "Water world": "water world", "Ammonia world": "ammonia world"}

    def _note_notable(self, entry, state):
        """Keeps the bodies worth talking about, so 'what was the terraformable world in this system?' has an answer."""
        name = entry.get("BodyName")
        if not name or not entry.get("PlanetClass"):
            return
        kind = self.NOTABLE_CLASSES.get(entry.get("PlanetClass"))
        if entry.get("TerraformState") == "Terraformable":
            kind = ("terraformable " + kind) if kind else "terraformable world"
        if not kind:
            return
        if len(state.notable) > 200:
            state.notable.clear()
        state.notable[name] = {"kind": kind, "system": state.system or ""}
