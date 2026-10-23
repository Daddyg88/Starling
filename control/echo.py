"""
Stops her saying the same thing twice.

When you say "open the galaxy map" she presses the key and says "Opening the galaxy map". A moment later
the game tells her the galaxy map is open, which would normally make her announce it again.
So after she does something for you, she remembers which game events that will cause (the "echo") and
the event speaker stays quiet about them, once each, for a few seconds.
"""

import time

from core.event_bus import CRITICAL


class Echo:
    def __init__(self, clock=time.monotonic, seconds=6.0):
        self.clock = clock
        self.seconds = seconds
        self._expected = {}
        self._muted = {}

    def expect(self, names):
        until = self.clock() + self.seconds
        for name in names or ():
            self._expected[name] = until

    def mute(self, names, seconds):
        """Stay quiet about these events for a while (every time they happen), e.g. while a macro opens and closes a map."""
        until = self.clock() + seconds
        for name in names or ():
            self._muted[name] = until

    def cancel(self, names):
        """The press did not happen after all: forget what we expected."""
        for name in names or ():
            self._expected.pop(name, None)

    def consume(self, event):
        """True if this event is the echo of something she just did (and so should not be announced)."""
        if getattr(event, "priority", "") == CRITICAL:
            return False                        # safety warnings are never swallowed
        muted = self._muted.get(event.name)
        if muted is not None and self.clock() <= muted:
            return True
        until = self._expected.get(event.name)
        if until is None:
            return False
        del self._expected[event.name]
        return self.clock() <= until
