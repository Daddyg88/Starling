"""
The exobiology overlay: a small see-through box on top of the game, bottom left by default.

Shows one line per planet in the system that has life:
    [little planet]  A 3   2  [white flag][white flag]   ~4.2M
      planet name    signals   flags = could be NEW to your codex   estimated value (~ = a guess, no ~ = scanned)

The box is orange writing and an orange border on a see-through background (or a dark one, a setting).
It ignores the mouse (you can click through it) and disappears when you leave the system or say "hide the bio overlay".

After you map a planet with the detailed surface scanner the box changes to that one planet: one line per life form with a white
flag when it would be new to your codex and the value (x5 on a first footfall). A life form you have finished (three samples) gets a
line through it. It stays while that planet is your target or while the target does not change (you are landing); targeting something
else, or un-targeting it, brings the list back.

Two parts:
  * overlay_rows() / layout() are plain Python (tested). They decide WHAT is shown and WHERE.
  * BioOverlay is the tkinter window. It runs inside the dashboard window's loop and checks once a second.
The game must be in Borderless or Windowed mode: a window can't be drawn over a true full-screen game.
"""

import time

from core.logger import get_logger

log = get_logger("bio_overlay")

ORANGE = "#ff8c1a"
KEY = "#010101"             # this exact colour becomes see-through (Windows)
DARK = "#0b0b0b"
WHITE = "#ffffff"
MAX_ROWS = 8
CHECK_MS = 1000
TEST_SECONDS = 10

SIZES = {"Small": 10, "Medium": 12, "Large": 15}
TEST_ROWS = [
    {"body": "A 1", "count": 2, "value": 4200000, "new": 2, "known": False, "kind": "rocky", "species": [], "genera": []},
    {"body": "B 3 a", "count": 1, "value": 19010800, "new": 1, "known": True, "kind": "highmetalcontent", "species": ["Stratum Tectonicas"], "genera": ["Stratum"]},
    {"body": "C 2", "count": 3, "value": 5100000, "new": 0, "known": False, "kind": "icy", "species": [], "genera": []},
]


def short_credits(amount):
    """4200000 -> '4.2M', 850000 -> '850K', 0 -> '?'."""
    amount = int(amount or 0)
    if amount <= 0:
        return "?"
    if amount >= 1_000_000:
        return ("%.1f" % (amount / 1_000_000.0)).rstrip("0").rstrip(".") + "M"
    if amount >= 1000:
        return "%dK" % round(amount / 1000.0)
    return str(amount)


def overlay_rows(rows, limit=MAX_ROWS):
    """Turns the predictor's rows into what is drawn: (text pieces per line, 'and N more' or '')."""
    lines = []
    for row in list(rows)[:limit]:
        lines.append({
            "body": str(row.get("body") or "?"),
            "count": int(row.get("count") or 0),
            "flags": max(0, min(int(row.get("new") or 0), int(row.get("count") or 0), 6)),
            "value": ("" if row.get("known") else "~") + short_credits(row.get("value")),
            "kind": str(row.get("kind") or "rocky"),
        })
    more = len(rows) - len(lines)
    return lines, ("and %d more" % more if more > 0 else "")


TEST_FOCUS = {"body": "B 3 a", "kind": "icy", "lives": [
    {"name": "Stratum Tectonicas", "new": True, "done": False, "value": 19010800, "exact": True},
    {"name": "Fonticulua", "new": False, "done": True, "value": 3200000, "exact": False},
    {"name": "Bacterium", "new": True, "done": False, "value": 1200000, "exact": False}]}


def overlay_focus(view):
    """The detailed view as text pieces: the planet and one line per life form (flag = new to the codex, done = line through it)."""
    lines = []
    for life in (view.get("lives") or [])[:MAX_ROWS]:
        lines.append({"name": str(life.get("name") or "?"), "flag": bool(life.get("new")) and not life.get("done"),
                      "done": bool(life.get("done")),
                      "value": ("" if life.get("exact") else "~") + short_credits(life.get("value"))})
    return {"body": str(view.get("body") or "?"), "kind": str(view.get("kind") or "rocky"), "lives": lines}


def wanted_focus(settings, state, now=None, test_until=0.0):
    """The detailed single-planet view, or None to show the list."""
    now = time.monotonic() if now is None else now
    if test_until and now < test_until:
        return TEST_FOCUS if now >= test_until - TEST_SECONDS / 2 else None
    try:
        if not settings.get("overlay.bio_enabled", True):
            return None
        bio = getattr(state, "bio", None)
        if bio is None or getattr(bio, "hidden", False):
            return None
        return bio.focus_view()
    except Exception:
        log.exception("Could not read the detailed biology view")
        return None


def placement(screen_w, screen_h, box_w, box_h, left_percent, up_percent):
    """Top-left corner of the box. left_percent is the gap from the left edge, up_percent how far up from the bottom its bottom edge sits."""
    left_percent = min(95, max(0, float(left_percent)))
    up_percent = min(95, max(0, float(up_percent)))
    x = int(screen_w * left_percent / 100.0)
    y = int(screen_h - screen_h * up_percent / 100.0 - box_h)
    return max(0, min(x, screen_w - box_w)), max(0, min(y, screen_h - box_h))


def wanted(settings, state, now=None, test_until=0.0):
    """(rows to show, is it a test). Empty list = hide the box."""
    now = time.monotonic() if now is None else now
    if test_until and now < test_until:
        return TEST_ROWS, True
    try:
        if not settings.get("overlay.bio_enabled", True):
            return [], False
        bio = getattr(state, "bio", None)
        if bio is None or getattr(bio, "hidden", False):
            return [], False
        return bio.rows(), False
    except Exception:
        log.exception("Could not read the biology rows")
        return [], False


class BioOverlay:
    def __init__(self, root, settings, state_provider):
        self.root = root
        self.settings = settings
        self.state_provider = state_provider
        self.window = None
        self.canvas = None
        self.test_until = 0.0
        self._signature = None
        self._broken = False
        self.root.after(CHECK_MS, self._tick)

    def show_test(self, seconds=TEST_SECONDS):
        self.test_until = time.monotonic() + seconds
        self._signature = None

    def _tick(self):
        try:
            if not self._broken:
                self._update()
        except Exception:
            log.exception("The biology overlay failed; it is switched off for this session")
            self._broken = True
            self._hide()
        try:
            self.root.after(CHECK_MS, self._tick)
        except Exception:
            pass

    def _update(self):
        state = self.state_provider()
        settings = (self.settings.get("overlay.bio_x", 3), self.settings.get("overlay.bio_up", 25),
                    self.settings.get("overlay.bio_size", "Medium"), self.settings.get("overlay.bio_dark", False))
        view = wanted_focus(self.settings, state, test_until=self.test_until)
        if view is not None:
            focus = overlay_focus(view)
            signature = ("focus", focus["body"], focus["kind"], tuple((l["name"], l["flag"], l["done"], l["value"]) for l in focus["lives"]), settings)
            if signature != self._signature:
                self._signature = signature
                self._draw_focus(focus, settings)
            return
        rows, _ = wanted(self.settings, state, test_until=self.test_until)
        lines, more = overlay_rows(rows)
        signature = (tuple((l["body"], l["count"], l["flags"], l["value"], l["kind"]) for l in lines), more, settings)
        if not lines:
            if self._signature is not None:
                self._signature = None
                self._hide()
            return
        if signature == self._signature:
            return
        self._signature = signature
        self._draw(lines, more, settings)

    # ---- the window ----
    def _make_window(self):
        import tkinter as tk
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg=KEY)
        try:
            window.attributes("-transparentcolor", KEY)          # Windows only
        except Exception:
            pass
        canvas = tk.Canvas(window, bg=KEY, highlightthickness=0, bd=0)
        canvas.pack(fill="both", expand=True)
        self.window, self.canvas = window, canvas
        window.update_idletasks()
        self._click_through(window)

    @staticmethod
    def _click_through(window):
        """Windows: let the mouse and keyboard pass straight through to the game."""
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
            GWL_EXSTYLE, LAYERED, TRANSPARENT, TOOLWINDOW, NOACTIVATE = -20, 0x80000, 0x20, 0x80, 0x08000000
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | LAYERED | TRANSPARENT | TOOLWINDOW | NOACTIVATE)
        except Exception:
            pass            # not Windows: it still works, it just takes mouse clicks

    def _hide(self):
        if self.window is not None:
            try:
                self.window.withdraw()
            except Exception:
                pass

    def _draw(self, lines, more, settings):
        left, up, size_name, dark = settings
        size = SIZES.get(str(size_name), 12)
        if self.window is None:
            self._make_window()
        canvas = self.canvas
        canvas.delete("all")
        font = ("Segoe UI", size, "bold")
        small = ("Segoe UI", max(8, size - 2), "bold")
        row_h = int(size * 2.3)
        pad = 10
        width = int(size * 21)
        title_h = int(size * 2.0)
        height = title_h + row_h * len(lines) + (int(size * 1.6) if more else 0) + pad
        fill = DARK if dark else KEY
        canvas.configure(width=width, height=height)
        canvas.create_rectangle(1, 1, width - 2, height - 2, outline=ORANGE, width=2, fill=fill)
        canvas.create_text(pad + 2, title_h // 2 + 2, text="BIOLOGY", anchor="w", fill=ORANGE, font=small)
        y = title_h
        for line in lines:
            mid = y + row_h // 2
            self._planet(canvas, pad + size * 0.9, mid, size * 0.75, line["kind"])
            canvas.create_text(pad + size * 2.2, mid, text=line["body"], anchor="w", fill=ORANGE, font=font)
            canvas.create_text(pad + size * 7.2, mid, text=str(line["count"]), anchor="w", fill=ORANGE, font=font)
            for n in range(line["flags"]):
                self._flag(canvas, pad + size * 8.6 + n * size * 1.2, mid, size)
            canvas.create_text(width - pad, mid, text=line["value"], anchor="e", fill=ORANGE, font=font)
            y += row_h
        if more:
            canvas.create_text(pad + 2, y + int(size * 0.8), text=more, anchor="w", fill=ORANGE, font=small)
        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, top = placement(screen_w, screen_h, width, height, left, up)
        self.window.geometry("%dx%d+%d+%d" % (width, height, x, top))
        self.window.deiconify()
        self.window.attributes("-topmost", True)
        self.window.lift()

    def _draw_focus(self, focus, settings):
        left, up, size_name, dark = settings
        size = SIZES.get(str(size_name), 12)
        if self.window is None:
            self._make_window()
        canvas = self.canvas
        canvas.delete("all")
        font = ("Segoe UI", size, "bold")
        small = ("Segoe UI", max(8, size - 2), "bold")
        row_h = int(size * 2.3)
        pad = 10
        width = int(size * 21)
        title_h = int(size * 2.4)
        lives = focus["lives"]
        height = title_h + row_h * len(lives) + pad
        canvas.configure(width=width, height=height)
        canvas.create_rectangle(1, 1, width - 2, height - 2, outline=ORANGE, width=2, fill=DARK if dark else KEY)
        self._planet(canvas, pad + size * 0.9, title_h // 2 + 2, size * 0.75, focus["kind"])
        canvas.create_text(pad + size * 2.2, title_h // 2 + 2, text=focus["body"], anchor="w", fill=ORANGE, font=font)
        y = title_h
        for life in lives:
            mid = y + row_h // 2
            if life["flag"]:
                self._flag(canvas, pad + size * 0.6, mid, size)
            x = pad + size * 2.0
            canvas.create_text(x, mid, text=life["name"], anchor="w", fill=ORANGE, font=font)
            canvas.create_text(width - pad, mid, text=life["value"], anchor="e", fill=ORANGE, font=font)
            if life["done"]:      # finished (three samples): a line through the name and the value
                reach = x + len(life["name"]) * size * 0.62
                canvas.create_line(x - 2, mid, min(reach, width - pad - size * 3), mid, fill=ORANGE, width=2)
                canvas.create_line(width - pad - len(life["value"]) * size * 0.62, mid, width - pad, mid, fill=ORANGE, width=2)
            y += row_h
        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        px, top = placement(screen_w, screen_h, width, height, left, up)
        self.window.geometry("%dx%d+%d+%d" % (width, height, px, top))
        self.window.deiconify()
        self.window.attributes("-topmost", True)
        self.window.lift()

    @staticmethod
    def _planet(canvas, cx, cy, r, kind):
        """A tiny orange planet: a circle, with a few marks that hint at what kind it is."""
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=ORANGE, width=2)
        if "icy" in kind or "ice" in kind:
            canvas.create_line(cx - r * 0.5, cy - r * 0.2, cx + r * 0.2, cy - r * 0.7, fill=ORANGE, width=2)       # a glint
            canvas.create_line(cx - r * 0.1, cy + r * 0.2, cx + r * 0.6, cy - r * 0.3, fill=ORANGE, width=2)
        elif "metal" in kind:
            canvas.create_line(cx - r * 0.9, cy - r * 0.3, cx + r * 0.9, cy - r * 0.3, fill=ORANGE, width=1)       # bands
            canvas.create_line(cx - r * 0.9, cy + r * 0.3, cx + r * 0.9, cy + r * 0.3, fill=ORANGE, width=1)
        else:
            for dx, dy, rr in ((-0.35, -0.2, 0.22), (0.3, 0.25, 0.18), (0.25, -0.35, 0.12)):            # craters
                canvas.create_oval(cx + r * (dx - rr), cy + r * (dy - rr), cx + r * (dx + rr), cy + r * (dy + rr), outline=ORANGE)

    @staticmethod
    def _flag(canvas, x, cy, size):
        """A small white flag on a pole (drawn, so no special font is needed)."""
        h = size * 0.9
        top = cy - h / 2
        canvas.create_line(x, top, x, top + h, fill=WHITE, width=2)
        canvas.create_polygon(x, top, x + size * 0.7, top + h * 0.28, x, top + h * 0.56, fill=WHITE, outline=WHITE)
