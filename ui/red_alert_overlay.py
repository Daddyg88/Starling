"""The red alert filter: a steady red wash over the whole screen with a soft, thin red edge. It does NOT pulse (0.87.1): the player is in a fight.

Two see-through, click-through windows on the screen Elite is on (the game must be in Borderless or Windowed mode):
  * the TINT window: all red, but see-through (7 to 16%, by strength) so it works as a red filter over the view
  * the EDGE window: the middle is a see-through colour and the edge is a thin soft band of red that fades inward
While red alert is off nothing is drawn and she only checks once a second whether it has started.
The numbers come from plain tested functions (bands, edge_alpha, tint_alpha); the tkinter part is the thin outside.
"""

import time

from core.logger import get_logger
from ui import screens

log = get_logger("red_alert_overlay")

KEY = "#010101"                  # this exact colour becomes see-through (Windows)
IDLE_MS = 1000
ACTIVE_MS = 500                  # while it is on she only has to look for a change (screen moved, settings changed)
STRENGTH = {"Soft": (0.12, 0.07), "Medium": (0.20, 0.11), "Strong": (0.30, 0.16)}     # edge see-through level, tint see-through level
BANDS = 12


def edge_alpha(strength):
    """The edge's see-through level (0 = invisible, 1 = solid). Steady: it never pulses."""
    return STRENGTH.get(str(strength), STRENGTH["Medium"])[0]


def tint_alpha(strength):
    """The whole-screen red wash's see-through level."""
    return STRENGTH.get(str(strength), STRENGTH["Medium"])[1]


def band_width(width, height):
    """How thick the edge is: about 2.5% of the shorter side, never thinner than 20 pixels (it was 5% and 40 in 0.87.0)."""
    return max(20, int(min(width, height) * 0.025))


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
                    delay = ACTIVE_MS
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
        window.withdraw()                    # never let it appear (and take the game's focus) before it is set up
        window.overrideredirect(True)
        window.configure(bg=colour)
        window.update_idletasks()
        self._harden(window)
        return window

    @staticmethod
    def _hwnd(window):
        import ctypes
        return ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()

    def _harden(self, window):
        """Windows: makes sure the window can never take a click or the keyboard focus from the game. Called every time it is shown,
        because changing see-through settings in tkinter can quietly reset these (0.87.2: the first version lost them and the player
        got a mouse cursor and could not click). WS_EX_LAYERED | TRANSPARENT (clicks go through) | TOOLWINDOW | NOACTIVATE (never active)."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = self._hwnd(window)
            style = user32.GetWindowLongW(hwnd, -20)
            wanted = style | 0x80000 | 0x20 | 0x80 | 0x08000000
            if wanted != style:
                user32.SetWindowLongW(hwnd, -20, wanted)
        except Exception:
            pass

    def _put_on_top_without_focus(self, window):
        """Shows the window and keeps it on top WITHOUT activating it (tkinter's deiconify and -topmost can activate it)."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = self._hwnd(window)
            user32.ShowWindow(hwnd, 4)                                           # SW_SHOWNOACTIVATE
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # TOPMOST, no move, no size, no activate
        except Exception:
            try:
                window.deiconify()
            except Exception:
                pass

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
        try:
            self.tint.attributes("-alpha", tint_alpha(strength) if want_tint else 0.0)
            self.frame.attributes("-alpha", edge_alpha(strength) if want_glow else 0.0)
        except Exception:
            pass
        for window in (self.tint, self.frame):
            self._harden(window)                                 # again, after the see-through settings above (they can reset it)
            self._put_on_top_without_focus(window)
        self._shown = True

    def _hide(self):
        for window in (self.tint, self.frame):
            if window is not None:
                try:
                    window.withdraw()
                except Exception:
                    pass
        self._shown = False
