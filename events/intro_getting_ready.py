"""The stream intro is on: she is pretending to get ready (the hologram plays a getting-ready clip)."""

from events.base_event import BaseEvent
from core.event_bus import LOW


class IntroGettingReady(BaseEvent):
    """Made up by STARLING herself (streaming/intro.py publishes it on the bus); only the hologram listens."""
    name = "IntroGettingReady"
    priority = LOW
    source = "app"
    summary = "The stream intro: she is getting ready"
