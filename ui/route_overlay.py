"""
The route map overlay: a small see-through picture on the RIGHT of the screen showing the galaxy, its regions and your plotted
neutron route, so you can SEE that the route is a good one instead of trusting it blindly.

What it shows (all drawn by navigation/galaxy_map.py, which is plain tested Python):
  * the galaxy region borders as thin orange lines on a see-through background
  * the route: cyan = still to fly, dim cyan = already flown, yellow dots = waypoints, a yellow ring = the destination
  * the start of the route sits near one edge and the destination near the other; every time you pass a waypoint the map zooms in
  * a cyan ring for where you are, and words underneath: the stops left, the jumps left, how straight the route is, the regions crossed

Two parts, like the biology list:
  * route_scene() decides WHAT to show (plain Python, tested)
  * RouteOverlay is the tkinter window. It checks once a second and only redraws when something changed.
The game must be in Borderless or Windowed mode.
"""

import threading
import time

from core.logger import get_logger
from navigation import galaxy_map
from ui import screens

log = get_logger("route_overlay")

KEY = galaxy_map.KEY        # this exact colour becomes see-through (Windows)
BORDER = galaxy_map.ORANGE
CHECK_MS = 1000
RECT_EVERY_SECONDS = 5.0
TEST_SECONDS = 10
SIZES = {"Small": 240, "Medium": 300, "Large": 380}
MODES = ("route", "always", "off")
BACKFILL_LIMIT = 40          # at most this many positions are looked up when a saved route has none


def map_size(name):
    return SIZES.get(str(name), SIZES["Medium"])


def placement(screen_w, screen_h, box_w, box_h, right_percent, top_percent):
    """Top-left corner of the box. right_percent = gap from the right edge, top_percent = gap from the top."""
    right_percent = min(95, max(0, float(right_percent)))
    top_percent = min(95, max(0, float(top_percent)))
    x = int(screen_w - screen_w * right_percent / 100.0 - box_w)
    y = int(screen_h * top_percent / 100.0)
    return max(0, min(x, screen_w - box_w)), max(0, min(y, screen_h - box_h))


def fit_text(text, limit):
    text = str(text or "")
    return text if len(text) <= limit else text[:max(1, limit - 1)].rstrip() + "…"


FRESH_SECONDS = 25           # a new route is shown for this long even when a game screen (the galaxy map) is open


def wanted_mode(settings, state, follower, test_until=0.0, now=None, fresh=False, void_compass=False):
    """'test', 'route', 'empty' (always-on with no route) or None (hide the map). fresh = the route was only just plotted."""
    now = time.monotonic() if now is None else now
    if test_until and now < test_until:
        return "test"
    try:
        mode = str(settings.get("overlay.route_map", "route"))
        if void_compass and settings.get("overlay.route_hide_with_voidcompass", True):
            return None                      # Void Compass draws its own route: no second map on top of it
        if mode == "off" or getattr(state, "game_quit", False) or getattr(state, "route_map_hidden", False):
            return None
        if settings.get("overlay.route_cockpit_only", True) and getattr(state, "gui_focus", 0) and not fresh:
            return None                      # a game screen is open (galaxy map, station menus...): keep out of the way
        active = bool(follower is not None and getattr(follower, "active", False))
        if active:
            return "route"
        return "empty" if mode == "always" else None
    except Exception:
        log.exception("Could not decide whether to show the route map")
        return None


def route_scene(settings, state, follower, test_until=0.0, now=None, fresh=False, void_compass=False):
    """The scene to draw (see galaxy_map.build_scene), or None to hide the map."""
    mode = wanted_mode(settings, state, follower, test_until, now, fresh, void_compass)
    if mode is None:
        return None
    size = map_size(settings.get("overlay.route_size", "Medium"))
    here = getattr(state, "star_pos", None)
    if mode == "test":
        steps = galaxy_map.test_route()
        return galaxy_map.build_scene(steps, 1, (steps[0]["x"], steps[0]["y"], steps[0]["z"]), "Colonia (test)", 3, 5, size)
    if mode == "empty":
        return galaxy_map.build_scene([], 0, here, "", 0, 0, size)
    with follower._lock:
        waypoints = list(follower.waypoints)
        index, destination = follower.index, follower.destination
        jumps_left, stops_left = follower.total_jumps_left(), follower.stops_left()
    scene = galaxy_map.build_scene(waypoints, index, here, destination, jumps_left, stops_left, size)
    if not scene["has_route"]:
        scene["text"] = [("Route plotted to %s" % (destination or "?"), galaxy_map.TEXT),
                         ("Positions are still being looked up. If this stays, plot the route again.", galaxy_map.MUTED)]
    return scene


def backfill_positions(follower, coordinates, limit=BACKFILL_LIMIT, sleep=time.sleep):
    """A route saved before 0.77.26 has no positions. Looks them up (a few, politely) and saves. Returns how many were found."""
    found = 0
    with follower._lock:
        ahead = [w for w in follower.waypoints[follower.index:] if not galaxy_map.has_position(w)]
        todo = (ahead[-1:] + ahead[:-1])[:limit]          # the destination first: the map must at least show where you are going
    for waypoint in todo:
        position = coordinates(waypoint["system"])
        if position is not None:
            waypoint["x"], waypoint["y"], waypoint["z"] = position
            found += 1
        sleep(0.3)
    if found:
        follower.save()
    return found


class RouteOverlay:
    def __init__(self, root, settings, state_provider, follower_provider, void_provider=None):
        self.root = root
        self.settings = settings
        self.state_provider = state_provider
        self.follower_provider = follower_provider
        self.void_provider = void_provider or (lambda: False)     # True while Void Compass is running
        self.window = None
        self.canvas = None
        self.photo = None
        self.test_until = 0.0
        self._signature = None
        self._broken = False
        self._rect_cache = None
        self._rect = None
        self._backfilled_for = None
        self._fresh_key = None
        self._fresh_until = 0.0
        self.root.after(CHECK_MS, self._tick)

    def show_test(self, seconds=TEST_SECONDS):
        self.test_until = time.monotonic() + seconds
        self._signature = None

    def _void_running(self):
        try:
            return bool(self.void_provider())
        except Exception:
            return False

    def _tick(self):
        try:
            if not self._broken:
                self._update()
        except Exception:
            log.exception("The route map failed; it is switched off for this session")
            self._broken = True
            self._hide()
        try:
            self.root.after(CHECK_MS, self._tick)
        except Exception:
            pass

    def _screen_rect(self):
        now = time.monotonic()
        cached = self._rect_cache
        if cached is not None and now - cached[0] < RECT_EVERY_SECONDS:
            return cached[1]
        main = (self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        rect = screens.overlay_rect(self.settings.get("overlay.screen", "auto"), main)
        self._rect_cache = (now, rect)
        return rect

    def _maybe_backfill(self, follower):
        if follower is None or not getattr(follower, "active", False):
            return
        key = (follower.destination, len(follower.waypoints))
        if key == self._backfilled_for:
            return
        self._backfilled_for = key
        if all(galaxy_map.has_position(w) for w in follower.waypoints):
            return
        def work():
            try:
                from navigation.spansh import Spansh
                backfill_positions(follower, Spansh().coordinates)
            except Exception:
                log.exception("Could not look up positions for the route map")
        threading.Thread(target=work, daemon=True, name="route-map-positions").start()

    def _update(self):
        state = self.state_provider()
        follower = self.follower_provider()
        self._rect = self._screen_rect()
        self._maybe_backfill(follower)
        s = self.settings
        key = (getattr(follower, "destination", ""), len(getattr(follower, "waypoints", []))) if follower is not None and getattr(follower, "active", False) else None
        if key is not None and key != self._fresh_key:
            self._fresh_until = time.monotonic() + FRESH_SECONDS      # a brand new route: show it now, even over the galaxy map
        self._fresh_key = key
        fresh = time.monotonic() < self._fresh_until
        void = self._void_running()
        mode = wanted_mode(s, state, follower, self.test_until, fresh=fresh, void_compass=void)
        if mode is None:
            if self._signature is not None:
                self._signature = None
                self._hide()
            return
        here = getattr(state, "star_pos", None)
        here_key = tuple(int(v) for v in here) if here and len(here) == 3 else None
        have = sum(1 for w in getattr(follower, "waypoints", []) if galaxy_map.has_position(w)) if follower is not None else 0
        signature = (mode, getattr(follower, "index", 0), getattr(follower, "destination", ""), len(getattr(follower, "waypoints", [])),
                     have, getattr(follower, "jumps_left", 0), here_key, s.get("overlay.route_size", "Medium"),
                     s.get("overlay.route_right", 2), s.get("overlay.route_top", 10), self._rect, fresh)
        if signature == self._signature:
            return
        self._signature = signature
        scene = route_scene(s, state, follower, self.test_until, fresh=fresh, void_compass=void)
        if scene is None:
            self._hide()
            return
        self._draw(scene)

    # ---- the window ----
    def _make_window(self):
        import tkinter as tk
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg=KEY)
        try:
            window.attributes("-transparentcolor", KEY)
        except Exception:
            pass
        canvas = tk.Canvas(window, bg=KEY, highlightthickness=0, bd=0)
        canvas.pack(fill="both", expand=True)
        self.window, self.canvas = window, canvas
        window.update_idletasks()
        try:
            from ui.bio_overlay import BioOverlay
            BioOverlay._click_through(window)
        except Exception:
            pass

    def _hide(self):
        if self.window is not None:
            try:
                self.window.withdraw()
            except Exception:
                pass

    def _draw(self, scene):
        import tkinter as tk
        if self.window is None:
            self._make_window()
        canvas = self.canvas
        canvas.delete("all")
        size = scene["size"]
        line_h = 17
        lines = scene["text"]
        height = size + 8 + line_h * len(lines) + 6
        width = size
        canvas.configure(width=width, height=height)
        canvas.create_rectangle(1, 1, width - 2, height - 2, fill=KEY, outline=BORDER, width=2)       # see-through, orange frame
        self.photo = self._picture(tk, scene["background"])
        canvas.create_image(1, 1, image=self.photo, anchor="nw")
        for x1, y1, x2, y2, colour, w, dash in scene["lines"]:
            canvas.create_line(x1, y1, x2, y2, fill=colour, width=w, dash=dash or ())
        for x, y, r, fill, outline in scene["dots"]:
            canvas.create_oval(x - r, y - r, x + r, y + r, fill=fill or "", outline=outline or fill, width=2 if outline else 1)
        for x, y, text, colour, anchor in scene["labels"]:
            canvas.create_text(x, y, text=text, fill=colour, anchor=anchor, font=("Segoe UI", 8, "bold"))
        limit = max(24, int(size / 6.3))
        y = size + 10
        for text, colour in lines:
            canvas.create_text(8, y + line_h // 2, text=fit_text(text, limit), anchor="w", fill=colour, font=("Segoe UI", 9, "bold"))
            y += line_h
        origin_x, origin_y, screen_w, screen_h = self._rect or self._screen_rect()
        x, top = placement(screen_w, screen_h, width, height, self.settings.get("overlay.route_right", 2),
                           self.settings.get("overlay.route_top", 10))
        self.window.geometry("%dx%d+%d+%d" % (width, height, origin_x + x, origin_y + top))
        self.window.deiconify()
        self.window.attributes("-topmost", True)
        self.window.lift()

    @staticmethod
    def _picture(tk, rows):
        height, width = len(rows), len(rows[0]) if rows else 0
        photo = tk.PhotoImage(width=width, height=height)
        photo.put(" ".join("{" + " ".join(row) + "}" for row in rows))        # one call: much faster than a pixel at a time
        return photo
