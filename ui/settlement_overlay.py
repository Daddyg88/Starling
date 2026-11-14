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
ACTIVE_MS = 500                 # the "you are here" arrow follows you twice a second (Status.json changes about once a second)
ME = "#00e5ff"
TARGET = "#ff4fd8"
MAX_HEIGHT_SHARE = 0.62         # a turned map can be taller than it is wide: never taller than this share of the screen


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
                    delay = ACTIVE_MS if getattr(self.view, "position", None) else 1000
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

    def _draw_me(self):
        """You are here: a bright arrow (or a dot when the heading is not known), redrawn every tick. Only this one item changes."""
        self.canvas.delete("me")
        where = getattr(self.view, "position", None)
        geom = getattr(self, "_geom", None)
        if not where or geom is None:
            return
        project, width = geom
        x, y = project(where["x"], where["y"])
        size = max(8, int(width * 0.016))
        target = getattr(self.view, "target", None)
        if target:                                    # "find the power plant": a ring on it and a line from you to it
            tx, ty = project(target["x"], target["y"])
            ring = size * 1.4
            self.canvas.create_line(x, y, tx, ty, fill=TARGET, width=3, dash=(6, 4), arrow="last", arrowshape=(14, 16, 6), tags="me")
            self.canvas.create_oval(tx - ring, ty - ring, tx + ring, ty + ring, outline=TARGET, width=3, tags="me")
            if getattr(self, "_font", None) is not None:
                self.canvas.create_text(tx, ty - ring - 8, text=str(target.get("label") or ""), fill=TARGET, font=self._font, tags="me")
        angle = where.get("angle")
        if angle is None:
            self.canvas.create_oval(x - size / 2, y - size / 2, x + size / 2, y + size / 2, fill=ME, outline="#000000", width=2, tags="me")
            return
        import math
        points = []
        for turn, length in ((0, size * 1.3), (140, size), (180, size * 0.45), (220, size)):        # a pointed arrow
            a = math.radians(angle + turn)
            points += [x + math.sin(a) * length, y - math.cos(a) * length]
        self.canvas.create_polygon(points, fill=ME, outline="#000000", width=2, tags="me")

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
        turn = getattr(self.view, "turn", None)
        key = (x, y, w, h, self.view.current, None if turn is None else round(turn))
        if key != self._last or first:
            self._last = key
            tw, th = settlement_maps.turned_size(data, turn)
            width = int(min(w * WIDTH_SHARE, h * MAX_HEIGHT_SHARE * tw / th))
            height = int(width * th / tw)
            shape = settlement_maps.layout(data, width, height, turn)
            font = tkfont.Font(family="Segoe UI", size=-max(10, int(width * 0.022)), weight="bold")
            self.canvas.delete("all")
            self.canvas.configure(width=width, height=height)
            for x1, y1, x2, y2 in shape["ground"]:
                self.canvas.create_line(x1, y1, x2, y2, fill=settlement_maps.COLOURS["ground"], width=1)
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
            self._geom = (shape["project"], width)
        self._draw_me()
        if not self._shown:
            self.window.deiconify()
        self.window.attributes("-topmost", True)
        self.window.lift()
        self._harden(self.window)
        self._put_on_top_without_focus(self.window)
        if not self._shown:
            log.info("Settlement map %s shown", self.view.current)
        self._shown = True
