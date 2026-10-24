"""Which Power you are pledged to (Powerplay). Not spoken; "I want to go merit mining" uses it.

Powerplay        written when you load the game, if you are pledged: {"Power": "Aisling Duval", "Rank", "Merits"...}
PowerplayJoin    you pledged to a power
PowerplayDefect  you changed power: {"FromPower", "ToPower"}
PowerplayLeave   you left your power
"""

from events.base_event import BaseEvent
from core.event_bus import LOW


def _name(value):
    return value.strip() if isinstance(value, str) and value.strip() else None


class Powerplay(BaseEvent):
    name = "Powerplay"
    priority = LOW
    announce = False

    def update_state(self, entry, state):
        power = _name(entry.get("Power"))
        if power:
            state.power = power


class PowerplayJoin(BaseEvent):
    name = "PowerplayJoin"
    priority = LOW
    announce = False

    def update_state(self, entry, state):
        power = _name(entry.get("Power"))
        if power:
            state.power = power


class PowerplayDefect(BaseEvent):
    name = "PowerplayDefect"
    priority = LOW
    announce = False

    def update_state(self, entry, state):
        power = _name(entry.get("ToPower"))
        if power:
            state.power = power


class PowerplayLeave(BaseEvent):
    name = "PowerplayLeave"
    priority = LOW
    announce = False

    def update_state(self, entry, state):
        state.power = None
