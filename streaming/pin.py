"""The comment on the screen: one chat message shown over the game, like a YouTube "highlighted comment".

Two ways in, one shared box (plain Python, no screen: the overlay window in ui/chat_pin_overlay.py only draws what it holds):
  * YOU click a line in the Starling chat window -> pinned; click it again (or another line) -> unpinned (a "manual" pin).
  * SHE picks a comment to answer (a chime-in, a chat question, a stream-intro reply) -> shown just before she replies and taken
    away again a moment after she has finished speaking (an "auto" pin). A manual pin is not lost by that: it comes back after.
"""
import threading
import time

from core.logger import get_logger

log = get_logger("chat_pin")

MAX_CHARS = 220               # a longer comment is cut here
AUTO_MAX_SECONDS = 45.0       # an auto pin never stays longer than this, whatever happens
AUTO_UNSPOKEN_SECONDS = 25.0  # ... and goes after this if she never actually said anything (nothing to wait for)
AFTER_SPEECH_SECONDS = 1.2    # it stays this long after she stops talking


def shorten(text, limit=MAX_CHARS):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


class ChatPin:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self._lock = threading.Lock()
        self.manual = None
        self.auto = None
        self.version = 0                  # goes up on every change, so the overlay knows when to redraw

    # ---- you ----
    def toggle(self, seq, user, text, platform=""):
        """A click on a chat line. Returns True if it is pinned now, False if it was unpinned."""
        with self._lock:
            if self.manual is not None and self.manual["seq"] == seq:
                self.manual = None
                self.version += 1
                return False
            self.manual = {"seq": seq, "user": str(user or ""), "text": shorten(text), "platform": str(platform or "")}
            self.version += 1
            return True

    def clear_manual(self):
        with self._lock:
            if self.manual is not None:
                self.manual = None
                self.version += 1

    def pinned_seq(self):
        with self._lock:
            return self.manual["seq"] if self.manual is not None else None

    # ---- her ----
    def show_for_reply(self, user, text, platform=""):
        """She is about to answer this comment."""
        with self._lock:
            self.auto = {"seq": None, "user": str(user or ""), "text": shorten(text), "platform": str(platform or ""),
                         "shown_at": self.clock(), "spoke": False, "quiet_since": None}
            self.version += 1
        log.info("Showing the comment she is answering (from %s)", user)

    def settle(self, speaking):
        """Called by the overlay a few times a second with 'is she talking?'. Takes the auto pin away once she has answered."""
        with self._lock:
            item = self.auto
            if item is None:
                return
            now = self.clock()
            done = False
            if speaking:
                item["spoke"] = True
                item["quiet_since"] = None
            elif item["spoke"]:
                if item["quiet_since"] is None:
                    item["quiet_since"] = now
                done = now - item["quiet_since"] >= AFTER_SPEECH_SECONDS
            else:
                done = now - item["shown_at"] >= AUTO_UNSPOKEN_SECONDS
            if now - item["shown_at"] >= AUTO_MAX_SECONDS:
                done = True
            if done:
                self.auto = None
                self.version += 1

    def clear_auto(self):
        with self._lock:
            if self.auto is not None:
                self.auto = None
                self.version += 1

    # ---- the overlay ----
    def current(self):
        """(user, text, platform) of what should be on screen, or None. Her pick wins while she is answering it."""
        with self._lock:
            item = self.auto or self.manual
            return (item["user"], item["text"], item["platform"]) if item else None
