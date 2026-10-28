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
BLUE = "#3da5ff"            # found in another region but not in this one
YELLOW = "#ffd42a"          # never found anywhere
TONES = {"never": YELLOW, "elsewhere": BLUE, "here": ORANGE}      # text colour; flags use the first two
MAX_ROWS = 8
MAX_INLINE_FLAGS = 4         # up to this many flags the value sits on the same line
CHECK_MS = 1000
TEST_SECONDS = 10

SIZES = {"Small": 10, "Medium": 12, "Large": 15}
TEST_ROWS = [
    {"body": "A 1", "count": 2, "value": 4200000, "new": 2, "flags": ["never", "elsewhere"], "known": False, "low": 1000000, "high": 19000000, "kind": "rocky", "species": [], "genera": []},
    {"body": "B 3 a", "count": 1, "value": 19010800, "new": 1, "flags": ["elsewhere"], "known": True, "kind": "highmetalcontent", "species": ["Stratum Tectonicas"], "genera": ["Stratum"]},
    {"body": "C 2", "count": 3, "value": 5100000, "new": 0, "flags": [], "known": False, "kind": "icy", "species": [], "genera": []},
]


def short_credits(amount):
    """4200000 -> '4.2M', 850000 -> '850K', 0 -> '?'."""
    amount = int(amount or 0)
    if amount <= 0:
        return "?"
    if amount >= 1_000_000_000:
        return ("%.1f" % (amount / 1_000_000_000.0)).rstrip("0").rstrip(".") + "B"
    if amount >= 1_000_000:
        return ("%.1f" % (amount / 1_000_000.0)).rstrip("0").rstrip(".") + "M"
    if amount >= 1000:
        return "%dK" % round(amount / 1000.0)
    return str(amount)


FLAG_COLORS = {"never": YELLOW, "elsewhere": BLUE}


def short_range(low, high, exact=False):
    """'1M-19M' / '800K-19M' (a guess is marked ~); one number when the two are close or the price is exact."""
    low, high = int(low or 0), int(high or 0)
    if exact or high <= 0 or low <= 0 or high <= low * 1.15:
        return ("" if exact else "~") + short_credits(high if exact else (low + high) // 2 or high)
    a, b = short_credits(low), short_credits(high)
    if a[-1] == b[-1] and a[-1] in "MKB":
        a = a[:-1]
    return "~%s-%s" % (a, b)


def overlay_rows(rows, limit=MAX_ROWS):
    """Turns the predictor's rows into what is drawn: (text pieces per line, 'and N more' or '')."""
    lines = []
    for row in list(rows)[:limit]:
        count = int(row.get("count") or 0)
        statuses = list(row["flags"]) if isinstance(row.get("flags"), list) else ["never"] * int(row.get("new") or 0)
        statuses = [s for s in statuses if s in ("never", "elsewhere")][:max(0, min(count, 12))]                # a planet can have up to twelve signals
        lines.append({
            "body": str(row.get("body") or "?"),
            "count": count,
            "flags": len(statuses),
            "two_line": len(statuses) > MAX_INLINE_FLAGS,        # many flags: the value goes on a second line so nothing is squashed
            "flag_colors": [FLAG_COLORS[s] for s in statuses],
            "tone": "never" if "never" in statuses else ("elsewhere" if statuses else "here"),
            "value": short_credits(row.get("value")) if row.get("known") else (
                short_range(row.get("low"), row.get("high")) if row.get("high") else "~" + short_credits(row.get("value"))),
            "kind": str(row.get("kind") or "rocky"),
        })
    more = len(rows) - len(lines)
    return lines, ("and %d more" % more if more > 0 else "")


TEST_FOCUS = {"body": "B 3 a", "kind": "icy", "lives": [
    {"name": "Stratum Tectonicas", "new": True, "status": "never", "tone": "never", "done": False, "value": 19010800, "exact": True},
    {"name": "Fonticulua", "new": False, "status": "here", "tone": "never", "done": True, "value": 3200000, "exact": True},
    {"name": "Bacterium", "new": True, "status": "elsewhere", "tone": "elsewhere", "done": False, "value": 1200000, "low": 1000000, "high": 2800000, "exact": False}]}


def overlay_focus(view):
    """The detailed view as text pieces: the planet and one line per life form (flag = new to the codex, done = line through it)."""
    lines = []
    for life in (view.get("lives") or [])[:MAX_ROWS]:
        status = "here" if life.get("done") else str(life.get("status") or ("never" if life.get("new") else "here"))
        lines.append({"name": str(life.get("name") or "?"), "flag": status in ("never", "elsewhere"), "status": status,
                      "done": bool(life.get("done")),
                      "tone": str(life.get("tone") or status),
                      "value": short_credits(life.get("value")) if life.get("exact") else (
                          short_range(life.get("low"), life.get("high")) if life.get("high") else "~" + short_credits(life.get("value")))})
    return {"body": str(view.get("body") or "?"), "kind": str(view.get("kind") or "rocky"), "lives": lines}


def _leaving(bio):
    """True from the moment a hyperspace jump starts (not when you arrive), so the box is gone before the screen goes white."""
    check = getattr(bio, "is_leaving", None)
    return bool(check()) if check is not None else False


def wanted_focus(settings, state, now=None, test_until=0.0):
    """The detailed single-planet view, or None to show the list."""
    now = time.monotonic() if now is None else now
    if test_until and now < test_until:
        return TEST_FOCUS if now >= test_until - TEST_SECONDS / 2 else None
    try:
        if getattr(state, "game_quit", False) or not settings.get("overlay.bio_enabled", True):
            return None
        bio = getattr(state, "bio", None)
        if bio is None or getattr(bio, "hidden", False) or _leaving(bio):
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
        if getattr(state, "game_quit", False) or not settings.get("overlay.bio_enabled", True):
            return [], False
        bio = getattr(state, "bio", None)
        if bio is None or getattr(bio, "hidden", False) or _leaving(bio):
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
            signature = ("focus", focus["body"], focus["kind"], tuple((l["name"], l["status"], l["tone"], l["done"], l["value"]) for l in focus["lives"]), settings)
            if signature != self._signature:
                self._signature = signature
                self._draw_focus(focus, settings)
            return
        rows, _ = wanted(self.settings, state, test_until=self.test_until)
        lines, more = overlay_rows(rows)
        signature = (tuple((l["body"], l["count"], tuple(l["flag_colors"]), l["value"], l["kind"]) for l in lines), more, settings)
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
        width = int(size * 23)
        title_h = int(size * 2.0)
        extra_h = int(size * 1.5)         # the second line of a planet with many flags
        height = title_h + sum(row_h + (extra_h if l.get("two_line") else 0) for l in lines) + (int(size * 1.6) if more else 0) + pad
        fill = DARK if dark else KEY
        canvas.configure(width=width, height=height)
        canvas.create_rectangle(1, 1, width - 2, height - 2, outline=ORANGE, width=2, fill=fill)
        canvas.create_text(pad + 2, title_h // 2 + 2, text="BIOLOGY", anchor="w", fill=ORANGE, font=small)
        y = title_h
        for line in lines:
            mid = y + row_h // 2
            two = bool(line.get("two_line"))
            self._planet(canvas, pad + size * 0.9, mid, size * 0.75, line["kind"])
            tone = TONES[line["tone"]]
            canvas.create_text(pad + size * 2.2, mid, text=line["body"], anchor="w", fill=tone, font=font)
            canvas.create_text(pad + size * 7.2, mid, text=str(line["count"]), anchor="w", fill=tone, font=font)
            flags = line["flag_colors"]
            step = min(size * 1.2, (width - 2 * pad - size * 8.6) / max(1, len(flags)))      # twelve flags still fit
            for n, colour in enumerate(flags):
                self._flag(canvas, pad + size * 8.6 + n * step, mid, size, colour)
            if two:
                canvas.create_text(width - pad, mid + row_h // 2 + extra_h // 2 - int(size * 0.5), text=line["value"], anchor="e", fill=tone, font=font)
            else:
                canvas.create_text(width - pad, mid, text=line["value"], anchor="e", fill=tone, font=font)
            y += row_h + (extra_h if two else 0)
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
        width = int(size * 23)
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
            tone = TONES.get(life["tone"], ORANGE)             # a form never found anywhere stays yellow, even while you sample it
            if life["flag"]:
                self._flag(canvas, pad + size * 0.6, mid, size, TONES.get(life["status"], ORANGE))
            x = pad + size * 2.0
            canvas.create_text(x, mid, text=life["name"], anchor="w", fill=tone, font=font)
            canvas.create_text(width - pad, mid, text=life["value"], anchor="e", fill=tone, font=font)
            if life["done"]:      # finished (three samples): a line through the name and the value
                reach = x + len(life["name"]) * size * 0.62
                canvas.create_line(x - 2, mid, min(reach, width - pad - size * 3), mid, fill=tone, width=2)
                canvas.create_line(width - pad - len(life["value"]) * size * 0.62, mid, width - pad, mid, fill=tone, width=2)
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
    def _flag(canvas, x, cy, size, colour=WHITE):
        """A small flag on a pole (drawn, so no special font is needed): yellow = never found, blue = found in another region."""
        h = size * 0.9
        top = cy - h / 2
        canvas.create_line(x, top, x, top + h, fill=colour, width=2)
        canvas.create_polygon(x, top, x + size * 0.7, top + h * 0.28, x, top + h * 0.56, fill=colour, outline=colour)
