"""You flew through a neutron or white dwarf jet cone."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class JetConeBoost(BaseEvent):
    name = "JetConeBoost"
    priority = NORMAL
    keep = ("BoostValue",)
    summary = "Jet cone boost x{BoostValue:.1f}"
