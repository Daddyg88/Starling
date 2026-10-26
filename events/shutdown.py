"""The game is closing."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class Shutdown(BaseEvent):
    name = "Shutdown"
    priority = NORMAL
    summary = "Game shutting down"

    def update_state(self, entry, state):
        state.game_quit = True            # every overlay hides
        try:
            state.bio.reset()             # and the biology memory of the system is dropped
        except Exception:
            pass
