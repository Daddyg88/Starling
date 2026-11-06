"""Remembers where the dashboard window was (which screen, how big) and puts it back there at the next start.

The pure parts (reading and checking a geometry text such as '1360x860+120+60') are separate from the tkinter parts so they
can be tested without a screen."""
import re

from core.logger import get_logger

log = get_logger("window")

_PATTERN = re.compile(r"^(\d+)x(\d+)([+-]-?\d+)([+-]-?\d+)$")
VISIBLE_MARGIN = 120          # at least this much of the window must be on a screen, so it can always be grabbed


def parse_geometry(text):
    """'1360x860+120+60' -> (1360, 860, 120, 60); None if it is not that shape."""
    match = _PATTERN.match(str(text or "").strip())
    if not match:
        return None
    width, height = int(match.group(1)), int(match.group(2))
    x, y = int(match.group(3).replace("+", "")), int(match.group(4).replace("+", ""))
    return width, height, x, y


def make_geometry(width, height, x, y):
    return "%dx%d%s%d%s%d" % (width, height, "+" if x >= 0 else "-", abs(x), "+" if y >= 0 else "-", abs(y))


def usable_geometry(text, screen, minimum=(1000, 640)):
    """The saved geometry if it still fits the screens, else None.

    `screen` is the whole desktop as (left, top, width, height) - it can start at a negative number when a second
    monitor sits to the left of or above the main one. A monitor that has been unplugged since makes the position invalid,
    so then she starts on the default screen instead of somewhere unreachable."""
    parsed = parse_geometry(text)
    if parsed is None:
        return None
    width, height, x, y = parsed
    left, top, screen_width, screen_height = screen
    if width < minimum[0] or height < minimum[1]:
        return None
    width, height = min(width, screen_width), min(height, screen_height)
    on_screen = (x + VISIBLE_MARGIN <= left + screen_width and x + width - VISIBLE_MARGIN >= left
                 and y >= top and y + VISIBLE_MARGIN <= top + screen_height)
    if not on_screen:
        return None
    return make_geometry(width, height, x, y)


def desktop_area(root):
    """(left, top, width, height) of all screens together."""
    try:
        import ctypes
        metrics = ctypes.windll.user32.GetSystemMetrics            # 76/77 = left/top of the virtual screen, 78/79 = its size
        width, height = metrics(78), metrics(79)
        if width > 0 and height > 0:
            return metrics(76), metrics(77), width, height
    except Exception:
        pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


class WindowMemory:
    """Keeps the last normal (not maximised) position of a tkinter window and saves it in settings."""

    def __init__(self, root, settings):
        self.root = root
        self.settings = settings
        self._last = ""
        self._job = None

    def restore(self):
        """Call before the window is shown. Returns True if an earlier position was put back."""
        saved = self.settings.get("window.geometry", "")
        usable = usable_geometry(saved, desktop_area(self.root))
        if usable:
            self.root.geometry(usable)
            self._last = usable
        if self.settings.get("window.maximised", False):
            try:
                self.root.after(200, lambda: self.root.state("zoomed"))
            except Exception:
                pass
        self.root.bind("<Configure>", self._moved, add="+")
        return bool(usable)

    def _moved(self, event):
        if event.widget is not self.root:
            return
        if self._job is not None:
            try:
                self.root.after_cancel(self._job)
            except Exception:
                pass
        self._job = self.root.after(500, self._remember)

    def _remember(self):
        self._job = None
        try:
            if self.root.state() == "normal":
                self._last = self.root.geometry()
        except Exception:
            pass

    def save(self):
        """Call when the window is closing."""
        try:
            maximised = self.root.state() == "zoomed"
            if not maximised:
                self._last = self.root.geometry()
            self.settings.set("window.geometry", self._last)
            self.settings.set("window.maximised", maximised)
            self.settings.save()
        except Exception:
            log.warning("Could not remember the window position", exc_info=True)
