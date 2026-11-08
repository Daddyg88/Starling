"""The red alert glow: a pulsing red frame around the edge of the screen and a very faint red tint over the view.

Two see-through, click-through windows on the screen Elite is on (the game must be in Borderless or Windowed mode):
  * the FRAME window: the middle is a see-through colour, the edge is bands of red from bright (outside) to dark (inside); the whole
    window's see-through level swings up and down about once a second, which is the pulse
  * the TINT window: all red, but so see-through (about 6%) that it only warms the view
While red alert is off nothing is drawn and she only checks once a second whether it has started.
The drawing numbers come from plain tested functions (bands, pulse_alpha); the tkinter part is the thin outside.
"""

import math
import time

from core.logger import get_logger
from ui import screens

log = get_logger("red_alert_overlay")

KEY = "#010101"                  # this exact colour becomes see-through (Windows)
IDLE_MS = 1000
PULSE_MS = 70                    # about 14 frames a second while it is on
PULSE_SECONDS = 1.2
STRENGTH = {"Soft": (0.10, 0.30, 0.04), "Medium": (0.16, 0.45, 0.06), "Strong": (0.24, 0.62, 0.09)}     # frame low, frame high, tint
BANDS = 16


def pulse_alpha(strength, seconds):
    """The frame's see-through level (0 = invisible, 1 = solid) at a moment: a smooth swing between the low and high value."""
    low, high, _tint = STRENGTH.get(str(strength), STRENGTH["Medium"])
    swing = (math.sin(seconds * 2 * math.pi / PULSE_SECONDS) + 1.0) / 2.0
    return round(low + (high - low) * swing, 3)


def tint_alpha(strength):
    return STRENGTH.get(str(strength), STRENGTH["Medium"])[2]


def band_width(width, height):
    """How thick the glowing edge is: about 5% of the shorter side, never thinner than 40 pixels."""
    return max(40, int(min(width, height) * 0.05))


def bands(width, height):
    """[(left, top, right, bottom, colour)] from the outside in: each is the outline of a rectangle, bright red at the edge, darker inside."""
    thick = band_width(width, height)
    each = max(1, thick // BANDS)
    out = []
    for i in range(BANDS):
        fade = i / float(BANDS - 1)
        red = int(255 - 150 * fade)
        green = int(24 * (1 - fade))
        out.append((i * each, i * each, width - i * each, height - i * each, "#%02x%02x%02x" % (red, green, green)))
    return out, each


class RedAlertOverlay:
    def __init__(self, root, settings, active_provider, tick=None):
        self.root = root
        self.settings = settings
        self.active_provider = active_provider
        self.tick_hook = tick
        self.frame = self.tint = None
        self.canvas = None
        self.test_until = 0.0
        self._rect = None
        self._rect_at = 0.0
        self._shown = False
        self._broken = False
        self._size = None
        self._hook_at = 0.0
        self.root.after(IDLE_MS, self._tick)

    def show_test(self, seconds=8):
        self.test_until = time.monotonic() + seconds

    def _wanted(self):
        try:
            return bool(self.active_provider()) or time.monotonic() < self.test_until
        except Exception:
            return False

    def _tick(self):
        delay = IDLE_MS
        try:
            now = time.monotonic()
            if self.tick_hook is not None and now - self._hook_at >= 1.0:          # housekeeping (the auto stand-down timer) once a second
                self._hook_at = now
                self.tick_hook()
            if not self._broken:
                if self._wanted() and (self.settings.get("red_alert.glow", True) or self.settings.get("red_alert.tint", True)):
                    self._show()
                    delay = PULSE_MS
                elif self._shown:
                    self._hide()
        except Exception:
            log.exception("The red alert glow failed; it is switched off for this session")
            self._broken = True
            self._hide()
        try:
            self.root.after(delay, self._tick)
        except Exception:
            pass

    def _screen_rect(self):
        now = time.monotonic()
        if self._rect is None or now - self._rect_at > 5.0:
            main = (self.root.winfo_screenwidth(), self.root.winfo_screenheight())
            self._rect, self._rect_at = screens.overlay_rect(self.settings.get("overlay.screen", "auto"), main), now
        return self._rect

    def _make(self, colour):
        import tkinter as tk
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg=colour)
        window.update_idletasks()
        try:
            from ui.bio_overlay import BioOverlay
            BioOverlay._click_through(window)
        except Exception:
            pass
        return window

    def _show(self):
        import tkinter as tk
        x, y, w, h = self._screen_rect()
        strength = self.settings.get("red_alert.strength", "Medium")
        want_glow = bool(self.settings.get("red_alert.glow", True)) or time.monotonic() < self.test_until
        want_tint = bool(self.settings.get("red_alert.tint", True)) or time.monotonic() < self.test_until
        if self.tint is None:
            self.tint = self._make("#ff0000")
        if self.frame is None:
            self.frame = self._make(KEY)
            try:
                self.frame.attributes("-transparentcolor", KEY)
            except Exception:
                pass
            self.canvas = tk.Canvas(self.frame, bg=KEY, highlightthickness=0, bd=0)
            self.canvas.pack(fill="both", expand=True)
        geometry = "%dx%d+%d+%d" % (w, h, x, y)
        if self._size != (geometry, want_glow):
            self._size = (geometry, want_glow)
            self.tint.geometry(geometry)
            self.frame.geometry(geometry)
            self.canvas.delete("all")
            if want_glow:
                rings, each = bands(w, h)
                for left, top, right, bottom, colour in rings:
                    self.canvas.create_rectangle(left, top, right, bottom, outline=colour, width=each + 1)
        if not self._shown:
            self.tint.deiconify()
            self.frame.deiconify()
            self._shown = True
        try:
            self.tint.attributes("-alpha", tint_alpha(strength) if want_tint else 0.0)
            self.frame.attributes("-alpha", pulse_alpha(strength, time.monotonic()) if want_glow else 0.0)
            self.tint.attributes("-topmost", True)
            self.frame.attributes("-topmost", True)
        except Exception:
            pass

    def _hide(self):
        for window in (self.tint, self.frame):
            if window is not None:
                try:
                    window.withdraw()
                except Exception:
                    pass
        self._shown = False
