"""
Knows whether Elite is still running, so every overlay can go when you leave the game.

The journal says "Shutdown" on a normal exit, but not after a crash or a killed game, and the overlays used to stay on screen then.
This looks for the game's window every couple of seconds. When it has been gone for ABSENT_SECONDS (long enough to ride out the
game switching screen mode or loading), the game counts as closed: every overlay hides, and the journal state is told too
(state.game_quit), so the route map and the biology panel hide as well. The next jump or load-in shows them again.

Where the window list cannot be read (not Windows) nothing changes: the overlays go by the journal alone.
"""

import time

from core.logger import get_logger

log = get_logger("game_watch")

ABSENT_SECONDS = 8.0
POLL_MS = 2000
GAME_WORDS = ("elite - dangerous", "elite dangerous")
NOT_THE_GAME = ("launcher",)              # the launcher window has the game's name in it but is not the game

_closed = False


def game_closed():
    """True while the game is known to be closed. Overlays check this before they show."""
    return _closed


def set_closed(value):
    global _closed
    _closed = bool(value)


def looks_like_game(title):
    text = (title or "").lower()
    return any(word in text for word in GAME_WORDS) and not any(word in text for word in NOT_THE_GAME)


def list_titles():
    """The titles of the windows on screen (Windows), or None when that cannot be read."""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        titles = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def collect(handle, _):
            length = user32.GetWindowTextLengthW(handle)
            if length > 0:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(handle, buffer, length + 1)
                titles.append(buffer.value)
            return True

        user32.EnumWindows(callback_type(collect), 0)
        return titles
    except Exception:
        return None


class GameWatch:
    def __init__(self, state_getter, lister=list_titles, clock=time.monotonic, absent_seconds=ABSENT_SECONDS):
        self.state_getter = state_getter
        self.lister = lister
        self.clock = clock
        self.absent_seconds = absent_seconds
        self.last_seen = clock()
        self.closed = False

    def poll(self):
        """Look once. Returns True when the game counts as closed."""
        now = self.clock()
        try:
            titles = self.lister()
        except Exception:
            titles = None
        if titles is None:                                   # cannot tell: leave it to the journal
            self._set(False)
            return False
        if any(looks_like_game(t) for t in titles):
            self.last_seen = now
            self._set(False)
            return False
        if now - self.last_seen >= self.absent_seconds:
            self._set(True)
            state = self.state_getter()
            if state is not None and not getattr(state, "game_quit", False):
                state.game_quit = True                       # the route map and the biology panel hide too
                log.info("Elite's window has been gone for %.0f s: every overlay hides", self.absent_seconds)
            return True
        return self.closed

    def _set(self, value):
        self.closed = value
        set_closed(value)
