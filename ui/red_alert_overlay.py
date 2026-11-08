"""The red alert banner: a small, see-through "RED ALERT" in red text at the bottom centre of the screen, just under the
Disembark / launch buttons. No filter, no glow, no pulse (0.88.0): the player is in a fight and the screen is left alone.

One see-through, click-through window on the screen Elite is on (Borderless or Windowed mode). It is built like the biology box (a canvas on a see-through colour), and the 'clicks go through / never active' settings are re-applied each time it is shown (see _harden).
While red alert is off nothing is drawn and she only checks once a second whether it has started.
"""

import time

from core.logger import get_logger
from ui import screens

log = get_logger("red_alert_overlay")

KEY = "#010101"                  # this exact colour becomes see-through (Windows)
IDLE_MS = 1000
ACTIVE_MS = 500                  # while it is on she only has to look for a change (screen moved, settings changed)
TEXT = "RED ALERT"
RED = "#ff2a2a"
SIZES = {"Small": 0.022, "Medium": 0.030, "Large": 0.042}       # text height as a share of the screen height
CENTRE_Y = 0.945                 # the middle of the text, as a share of the screen height (the Disembark button is at about 0.87)


def font_pixels(size_name, height):
    """The text size in pixels for a screen height: scales with 1080p, 1440p, 4K and so on, never smaller than 14."""
    return max(14, int(height * SIZES.get(str(size_name), SIZES["Medium"])))


def place(width, height, text_width, text_height):
    """Where the banner window goes inside the screen: (left, top), centred across and CENTRE_Y down."""
    return int((width - text_width) / 2), int(height * CENTRE_Y - text_height / 2)


class RedAlertOverlay:
    def __init__(self, root, settings, active_provider, tick=None):
        self.root = root
        self.settings = settings
        self.active_provider = active_provider
        self.tick_hook = tick
        self.window = None
        self.canvas = None
        self._font = None
        self.test_until = 0.0
        self._rect = None
        self._rect_at = 0.0
        self._shown = False
        self._broken = False
        self._last = None
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
                if self._wanted() and (self.settings.get("red_alert.banner", True) or now < self.test_until):
                    self._show()
                    delay = ACTIVE_MS
                elif self._shown:
                    self._hide()
        except Exception:
            log.exception("The red alert banner failed; it is switched off for this session")
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

    def _make(self):
        """Built the same way as the biology box (ui/bio_overlay.py), which is known to show over Elite: a normal borderless window with
        a see-through colour and a canvas. Then the click-through / never-active settings are added in _harden."""
        import tkinter as tk
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg=KEY)
        try:
            window.attributes("-transparentcolor", KEY)          # Windows only
        except Exception:
            pass
        self.canvas = tk.Canvas(window, bg=KEY, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        window.update_idletasks()
        self._harden(window)
        return window

    @staticmethod
    def _hwnd(window):
        import ctypes
        return ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()

    def _harden(self, window):
        """Windows: makes sure the window can never take a click or the keyboard focus from the game. Called every time it is shown,
        because changing see-through settings in tkinter can quietly reset these. WS_EX_LAYERED | TRANSPARENT (clicks go through) |
        TOOLWINDOW | NOACTIVATE (never the active window)."""
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
        import tkinter.font as tkfont
        x, y, w, h = self._screen_rect()
        size = self.settings.get("red_alert.size", "Medium")
        first = self.window is None
        if first:
            self.window = self._make()
        key = (x, y, w, h, size)
        if key != self._last or first:
            self._last = key
            font = tkfont.Font(family="Segoe UI", size=-font_pixels(size, h), weight="bold")
            tw, th = font.measure(TEXT) + 8, font.metrics("linespace") + 4
            left, top = place(w, h, tw, th)
            self.canvas.delete("all")
            self.canvas.configure(width=tw, height=th)
            self.canvas.create_text(tw // 2, th // 2, text=TEXT, fill=RED, font=font)
            self.window.geometry("%dx%d+%d+%d" % (tw, th, x + left, y + top))
            self._font = font                                     # keep a reference so tkinter does not drop it
        if not self._shown:
            self.window.deiconify()
        self.window.attributes("-topmost", True)
        self.window.lift()
        self._harden(self.window)
        self._put_on_top_without_focus(self.window)
        if not self._shown:
            log.info("RED ALERT banner shown on the screen at %d,%d (%dx%d)", x, y, w, h)
        self._shown = True

    def _hide(self):
        if self.window is not None:
            try:
                self.window.withdraw()
            except Exception:
                pass
        self._shown = False
