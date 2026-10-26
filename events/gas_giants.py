"""A green gas giant. The journal has no sign of it in the planet's Scan line: the game gives it its own codex entry
("$Codex_Ent_Green_Sudarsky_Class_I_Name;" / "...Class_II...", shown as "Green gas giant"). events/codex_entry.py makes this event from that."""

from core.event_bus import NORMAL
from events.base_event import BaseEvent


class GreenGasGiant(BaseEvent):
    name = "GreenGasGiant"
    priority = NORMAL
    source = "status"
    summary = "Green gas giant found in {System}"
