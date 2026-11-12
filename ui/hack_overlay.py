"""The hack panel: a small green-on-black "old computer" box on the screen while the hack runs (navigation/hack.py).

It shows the base name, what she is doing (CONNECTING / DECRYPTING / BASE MAPPED), a progress bar of blocks and a short checklist of
what she still needs ("Terminals 3/9", "Gun posts and supplies 1/4", "Ground covered 12/30"). It never shows coordinates.
Built like the red alert banner (ui/red_alert_overlay.py): one click-through window that never takes the mouse or the keyboard focus
from the game. Needs Elite in Borderless or Windowed mode. Settings: hack.overlay (on/off), hack.position (Left / Right / Top), hack.size.
"""
import time

from core.logger import get_logger
from ui.red_alert_overlay import RedAlertOverlay

log = get_logger("hack_overlay")

IDLE_MS = 1000
ACTIVE_MS = 500
PANEL = "#06100a"
GREEN = "#38ff78"
DIM = "#1f9a48"
WARN = "#ffd42a"
BAD = "#ff5a4a"
WIDTH_SHARE = {"Small": 0.16, "Medium": 0.20, "Large": 0.26}        # of the screen width
BAR_BLOCKS = 20
SPOTS = {"Left": (0.02, 0.36), "Right": (0.985, 0.64), "Top": (0.5, 0.11)}       # (x, y) as a share of the screen; Right means 'the right edge'


def bar_text(progress, blocks=BAR_BLOCKS):
    """The progress bar as text: [██████░░░░] 42%"""
    progress = max(0.0, min(1.0, float(progress or 0.0)))
    full = int(round(progress * blocks))
    return "%s%s %3d%%" % ("█" * full, "░" * (blocks - full), round(progress * 100))


def panel_rows(snap, tick=0):
    """[(text, colour)] for the panel, top to bottom. Pure, so it can be tested."""
    cursor = "_" if tick % 2 == 0 else " "
    status = str(snap.get("status") or "")
    colour = GREEN
    if snap.get("done"):
        colour = GREEN if snap.get("how") == "complete" else (WARN if snap.get("how") in ("timeout", "aborted") else BAD)
    rows = [("EAST ORION COMPANY", WARN), ("SECURE LINK", DIM),
            (str(snap.get("name") or "")[:34], GREEN), ("> " + status + ("" if snap.get("done") else cursor), colour),
            (bar_text(snap.get("progress")), colour)]
    for label, found, needed in snap.get("items") or []:
        rows.append(("%-24s %2d/%-2d" % (label, found, needed), GREEN if found >= needed else DIM))
    return rows


class HackOverlay(RedAlertOverlay):
    def __init__(self, root, settings, hack_provider):
        self.hack_provider = hack_provider
        self._count = 0
        super().__init__(root, settings, active_provider=lambda: self._snap() is not None)

    def _snap(self):
        try:
            if not self.settings.get("hack.overlay", True):
                return None
            hack = self.hack_provider()
            return hack.snapshot() if hack is not None else None
        except Exception:
            return None

    def _wanted(self):
        return self._snap() is not None

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
            log.exception("The hack panel failed; it is switched off for this session")
            self._broken = True
            self._hide()
        try:
            self.root.after(delay, self._tick)
        except Exception:
            pass

    def _show(self):
        import tkinter.font as tkfont
        snap = self._snap()
        if snap is None:
            return
        x, y, w, h = self._screen_rect()
        first = self.window is None
        if first:
            self.window = self._make()
        self._count += 1
        size = str(self.settings.get("hack.size", "Medium"))
        width = int(w * WIDTH_SHARE.get(size, WIDTH_SHARE["Medium"]))
        pixel = max(11, int(width * 0.062))
        font = tkfont.Font(family="Consolas", size=-pixel, weight="bold")
        rows = panel_rows(snap, self._count // 1)
        pad = int(pixel * 0.7)
        line = int(pixel * 1.45)
        height = pad * 2 + line * len(rows)
        self.canvas.delete("all")
        self.canvas.configure(width=width, height=height)
        self.canvas.create_rectangle(1, 1, width - 2, height - 2, fill=PANEL, outline=DIM, width=2)
        for index, (text, colour) in enumerate(rows):
            self.canvas.create_text(pad, pad + line * index + line // 2, text=text, fill=colour, font=font, anchor="w")
        fx, fy = SPOTS.get(str(self.settings.get("hack.position", "Left")), SPOTS["Left"])
        left = int(w * fx) if fx < 0.9 else int(w * fx) - width
        if str(self.settings.get("hack.position", "Left")) == "Top":
            left = int(w * 0.5 - width / 2)
        top = int(h * fy)
        self.window.geometry("%dx%d+%d+%d" % (width, height, x + left, y + top))
        self._font = font
        if not self._shown:
            self.window.deiconify()
            log.info("Hack panel shown")
        self.window.attributes("-topmost", True)
        self.window.lift()
        self._harden(self.window)
        self._put_on_top_without_focus(self.window)
        self._shown = True
