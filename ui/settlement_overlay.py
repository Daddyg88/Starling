"""The settlement map: a see-through wireframe drawing on top of the game (terminals, locked doors, power regulator, alarm console).
Built like the red alert banner (ui/red_alert_overlay.py): one click-through window that never takes the keyboard from the game. (No writing on it: the credits are in maps/settlements/CREDITS.md, the README and the website.)
It stays until you say "hide the settlement map", or after AUTO_HIDE_SECONDS. What is drawn comes from navigation/settlement_maps.py.
Needs Elite in Borderless or Windowed mode."""
import time

from core.logger import get_logger
from navigation import settlement_maps
from ui.red_alert_overlay import KEY, RedAlertOverlay

log = get_logger("settlement_overlay")

WIDTH_SHARE = 0.34              # the map's width as a share of the screen width
RIGHT_MARGIN = 0.015
TOP_SHARE = 0.10
AUTO_HIDE_SECONDS = 900
IDLE_MS = 1000
ACTIVE_MS = 1000


class SettlementOverlay(RedAlertOverlay):
    def __init__(self, root, settings, maps, view):
        self.maps, self.view = maps, view
        super().__init__(root, settings, active_provider=lambda: self.view.current is not None)

    def _wanted(self):
        if self.view.current is None:
            return False
        if time.monotonic() - self.view.shown_at > AUTO_HIDE_SECONDS:
            self.view.current = None
            return False
        return True

    def _tick(self):
        delay = IDLE_MS
        try:
            if not self._broken:
                if self._wanted():
                    self._show()
                    delay = ACTIVE_MS
                elif self._shown:
                    self._hide()
        except Exception:
            log.exception("The settlement map failed; it is switched off for this session")
            self._broken = True
            self._hide()
        try:
            self.root.after(delay, self._tick)
        except Exception:
            pass

    def _show(self):
        import tkinter.font as tkfont
        data = self.maps.get(self.view.current)
        if data is None:
            self.view.current = None
            return
        x, y, w, h = self._screen_rect()
        first = self.window is None
        if first:
            self.window = self._make()
        key = (x, y, w, h, self.view.current)
        if key != self._last or first:
            self._last = key
            width = int(w * WIDTH_SHARE)
            height = int(width * float(data["size"][1]) / float(data["size"][0])) 
            shape = settlement_maps.layout(data, width, height)
            font = tkfont.Font(family="Segoe UI", size=-max(10, int(width * 0.022)), weight="bold")
            self.canvas.delete("all")
            self.canvas.configure(width=width, height=height)
            for x1, y1, x2, y2 in shape["lines"]:
                self.canvas.create_line(x1, y1, x2, y2, fill=settlement_maps.COLOURS["building"], width=2)
            for cx, cy, r in shape["circles"]:
                self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=settlement_maps.COLOURS["building"], width=1)
            for text, lx, ly in shape["labels"]:
                self.canvas.create_text(lx, ly, text=text, fill=settlement_maps.COLOURS["label"], font=font)
            radius = max(5, int(width * 0.008))
            for mx, my, colour, text in shape["markers"]:
                self.canvas.create_oval(mx - radius, my - radius, mx + radius, my + radius, fill=colour, outline="#000000")
                if text:
                    self.canvas.create_text(mx, my, text=text, fill="#000000" if colour in ("#c6ff00", "#ffd42a", "#7fd0ff") else "#ffffff", font=font)
            left = x + w - width - int(w * RIGHT_MARGIN)
            top = y + int(h * TOP_SHARE)
            self.window.geometry("%dx%d+%d+%d" % (width, height, left, top))
            self._font = font
        if not self._shown:
            self.window.deiconify()
        self.window.attributes("-topmost", True)
        self.window.lift()
        self._harden(self.window)
        self._put_on_top_without_focus(self.window)
        if not self._shown:
            log.info("Settlement map %s shown", self.view.current)
        self._shown = True
