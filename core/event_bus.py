"""
The event bus: STARLING's "announcement board".

One part of STARLING posts an announcement ("FuelScoop happened").
Any other part that cares has signed up to hear about it.
The parts never need to know about each other, so adding or
removing a feature can't break the others.

Priorities:
    "critical"  safety warnings (low fuel, hostiles, hull damage...)
    "normal"    ordinary events
    "low"       background chatter
"""

import threading
import time
from dataclasses import dataclass, field

from core.logger import get_logger

log = get_logger("event_bus")

CRITICAL = "critical"
NORMAL = "normal"
LOW = "low"
VALID_PRIORITIES = (CRITICAL, NORMAL, LOW)

# Sign up for this name to hear about EVERY event.
ALL_EVENTS = "*"


@dataclass
class Event:
    """One announcement."""
    name: str
    data: dict = field(default_factory=dict)
    priority: str = NORMAL
    timestamp: float = field(default_factory=time.time)


class EventBus:
    def __init__(self):
        self._subscribers = {}
        self._lock = threading.RLock()
        self.handler_errors = 0  # how many listeners have crashed so far

    def subscribe(self, event_name, callback):
        """Ask to be told when event_name happens. callback(event) is called."""
        with self._lock:
            listeners = self._subscribers.setdefault(event_name, [])
            if callback not in listeners:
                listeners.append(callback)

    def unsubscribe(self, event_name, callback):
        """Stop being told about event_name."""
        with self._lock:
            listeners = self._subscribers.get(event_name, [])
            if callback in listeners:
                listeners.remove(callback)

    def publish(self, event_name, data=None, priority=NORMAL):
        """Announce that something happened. Returns the Event."""
        if priority not in VALID_PRIORITIES:
            raise ValueError(
                "priority must be one of %s, not %r" % (VALID_PRIORITIES, priority)
            )
        event = Event(name=event_name, data=dict(data or {}), priority=priority)

        with self._lock:
            listeners = list(self._subscribers.get(event_name, []))
            listeners += list(self._subscribers.get(ALL_EVENTS, []))

        for callback in listeners:
            try:
                callback(event)
            except Exception:
                # One broken listener must never stop the others,
                # and must never crash the program.
                self.handler_errors += 1
                log.exception("A listener crashed while handling %s", event_name)
        return event
