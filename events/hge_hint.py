"""You arrived in a system whose faction state tends to give certain High Grade Emissions materials."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class HighGradeHint(BaseEvent):
    """Made up by STARLING herself from the FSDJump line (journal/hge_states.py): announced through the pending events."""
    name = "HighGradeHint"
    priority = LOW
    source = "status"
    summary = "{StarSystem} is in {State}: {Materials} are likely in high grade emissions"
