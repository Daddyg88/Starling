"""You arrived in a system nobody has discovered."""

from events.base_event import BaseEvent
from core.event_bus import NORMAL


class UndiscoveredSystem(BaseEvent):
    """Made up by STARLING herself (not a journal line): it is announced through processor.emit()."""
    name = "UndiscoveredSystem"
    priority = NORMAL
    source = "status"
    summary = "Nobody has discovered {StarSystem} yet"
