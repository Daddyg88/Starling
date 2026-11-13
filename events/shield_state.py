"""Your shields went down or came back up. SAFETY: always announced."""

from events.base_event import BaseEvent
from core.event_bus import CRITICAL


class ShieldState(BaseEvent):
    name = "ShieldState"
    priority = CRITICAL
    keep = ("ShieldsUp",)
    own_press = None          # set by core/app.py: a function(shields_up) that is True when her own auto-shields key press caused this line

    def handle(self, entry):
        data = super().handle(entry)
        try:
            hook = type(self).own_press
            if hook is not None and "ShieldsUp" in entry and hook(bool(entry["ShieldsUp"])):
                data["_silent"] = True            # she pressed the key herself: nothing to shout about (the game state is still updated)
        except Exception:
            pass
        return data

    def update_state(self, entry, state):
        if "ShieldsUp" in entry:
            state.shields_up = bool(entry["ShieldsUp"])

    def describe(self, data):
        return "Shields are back up" if data.get("ShieldsUp") else "Shields are DOWN"
