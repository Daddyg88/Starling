"""
Push-to-talk.

Modes (setting  ptt.mode):
    off      she listens all the time and waits for her name (the old way)
    hold     she only listens while you HOLD the button; let go and she acts on what you said
    toggle   press once to start listening, press again to stop

The button (setting  ptt.button) can be a keyboard key, a mouse side button or a joystick button (your X52).
While push-to-talk is on you do not need to say her name: the button already means "I'm talking to you".

This file only decides "is the microphone open right now?". The Listener asks it before every sound.
"""

import threading
import time

from core.logger import get_logger

log = get_logger("ptt")

OFF, HOLD, TOGGLE = "off", "hold", "toggle"
POLL_SECONDS = 0.02
IDLE_POLL_SECONDS = 0.3


class PushToTalk:
    def __init__(self, settings, reader, beep=None, clock=time.monotonic):
        self.settings = settings
        self.reader = reader
        self.beep = beep                 # beep(opening: bool), optional
        self.clock = clock
        self._open = False
        self._was_down = False
        self._thread = None
        self._running = False
        self._press_time = -99.0

    # ---- what the Listener asks ----
    def mode(self):
        mode = self.settings.get("ptt.mode", OFF)
        return mode if mode in (HOLD, TOGGLE) else OFF

    def button(self):
        return self.settings.get("ptt.button", "") or ""

    def enabled(self):
        """True when push-to-talk is on and a button has been chosen."""
        return self.mode() != OFF and bool(self.button())

    def is_open(self):
        return self._open if self.enabled() else True

    # ---- reading the button ----
    def poll_once(self):
        if not self.enabled():
            if self._open:
                self._open = False
            self._was_down = False
            return
        down = self.reader.is_down(self.button())
        if self.mode() == HOLD:
            if down != self._open:
                self._set(down)
        elif down and not self._was_down:                 # toggle: only the moment of pressing counts
            if self.clock() - self._press_time > 0.2:      # ignore contact bounce
                self._set(not self._open)
            self._press_time = self.clock()
        self._was_down = down

    def _set(self, opening):
        self._open = opening
        log.debug("Microphone %s", "open" if opening else "closed")
        if self.beep is not None and self.settings.get("ptt.beep", True):
            try:
                self.beep(opening)
            except Exception:
                log.exception("Beep failed")

    # ---- the little worker ----
    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="ptt", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _loop(self):
        while self._running:
            try:
                self.poll_once()
            except Exception:
                log.exception("Push-to-talk poll failed")
            time.sleep(POLL_SECONDS if self.enabled() else IDLE_POLL_SECONDS)


def windows_beep(opening):
    """A short high beep when the microphone opens and a low one when it closes."""
    try:
        import winsound
        winsound.Beep(1000 if opening else 600, 60)
    except Exception:
        pass
