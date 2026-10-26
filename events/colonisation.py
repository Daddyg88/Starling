"""
Colonies. The journal says when you claim a system with a colonisation ship, and when you give one up.
Nothing is spoken for these lines; journal/owned_systems.py keeps the list so she can welcome you home (OwnSystemArrival).
"""

from core.event_bus import NORMAL
from events.base_event import BaseEvent


class ColonisationSystemClaim(BaseEvent):
    name = "ColonisationSystemClaim"
    announce = False

    def update_state(self, entry, state):
        state.owned.claim(entry.get("StarSystem") or state.system, entry.get("SystemAddress"), entry.get("timestamp"))


class ColonisationSystemClaimRelease(BaseEvent):
    name = "ColonisationSystemClaimRelease"
    announce = False

    def update_state(self, entry, state):
        state.owned.release(entry.get("StarSystem") or state.system)


class OwnSystemArrival(BaseEvent):
    """Made up by STARLING when you arrive in a system you own."""
    name = "OwnSystemArrival"
    priority = NORMAL
    source = "status"
    summary = "Welcome back to {StarSystem}, one of your own systems"
