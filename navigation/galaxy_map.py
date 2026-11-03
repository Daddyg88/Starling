"""
THE ROUTE MAP: a top-down picture of the galaxy with its 42 regions and your plotted neutron route on it.

This file is plain Python with no window code, so it can be tested. ui/route_overlay.py draws what it makes.

How the picture is made
  * The region map (navigation/region_data.py) is a 2048 x 2048 grid; one cell is about 49 light years. It is read once and kept.
  * A "view" is the square patch of galaxy you look at: the whole galaxy for a long route, or just the part around the route for
    a short one, so a 150 ly hop is still visible.
  * build_scene() turns the view, the route and where you are into a "scene": a coloured background, lines, dots and words.
    The window (or a test) just draws the scene.

Galaxy coordinates: x goes east, z goes north (towards the galactic centre from Sol). On the picture north is up.
"""

import math
from dataclasses import dataclass

from navigation import regions as region_lookup
from navigation.region_data import regionmap, regions

CELL_LY = 4096.0 / 83.0                   # one cell of the region grid
GRID = len(regionmap)                     # 2048
X_MIN, Z_MIN = region_lookup.X0, region_lookup.Z0
GALAXY_SPAN = GRID * CELL_LY              # about 101,000 ly
MIN_SPAN_LY = 1500.0                      # never zoom in further than this
WHOLE_BELOW = 0.55                        # a route spanning more than this share of the galaxy shows the whole galaxy

OUTSIDE = "#050913"                       # space beyond the mapped regions
EDGE = "#8fb4d8"                          # region borders
AHEAD = "#35e0ff"                         # the route still to fly
BEHIND = "#4a6a86"                        # the part you have flown
NEUTRON = "#ffd23d"
FUEL = "#f4f7fb"
HERE = "#ffffff"
GOAL = "#ff4d6d"
LANDMARK = "#9fd3ff"
TEXT = "#e6f4ff"
MUTED = "#8ea3c7"
GOOD = "#3dffb0"
WARN = "#ffb84d"
BAD = "#ff6b6b"

LANDMARKS = (("Sol", 0.0, 0.0), ("Sgr A*", 25.2, 25899.0), ("Colonia", -9530.0, 19808.0))

_rows = None


def grid():
    """The region grid as 2048 rows of 2048 bytes (the region number of each cell). Built once, about 4 MB."""
    global _rows
    if _rows is None:
        _rows = [b"".join(bytes([value]) * run for run, value in row) for row in regionmap]
    return _rows


@dataclass(frozen=True)
class View:
    x: float          # west edge, light years
    z: float          # south edge
    span: float       # width and height

    @property
    def centre(self):
        return self.x + self.span / 2.0, self.z + self.span / 2.0


WHOLE = View(X_MIN, Z_MIN, GALAXY_SPAN)


def has_position(point):
    try:
        return point is not None and all(point.get(k) is not None for k in ("x", "y", "z")) and \
            all(math.isfinite(float(point[k])) for k in ("x", "y", "z"))
    except (TypeError, ValueError, AttributeError):
        return False


def fit_view(points, margin=0.22):
    """The view that shows all these (x, z) points with some room around them. Long routes get the whole galaxy."""
    points = [(float(x), float(z)) for x, z in points]
    if not points:
        return WHOLE
    xs, zs = [p[0] for p in points], [p[1] for p in points]
    span = max(max(xs) - min(xs), max(zs) - min(zs), 1.0)
    span = max(span * (1.0 + 2 * margin), MIN_SPAN_LY)
    if span >= GALAXY_SPAN * WHOLE_BELOW:
        return WHOLE
    centre_x, centre_z = (max(xs) + min(xs)) / 2.0, (max(zs) + min(zs)) / 2.0
    return View(centre_x - span / 2.0, centre_z - span / 2.0, span)


def to_pixel(view, size, x, z):
    """Galaxy (x, z) -> picture (column, row). North (larger z) is up."""
    scale = size / view.span
    return (float(x) - view.x) * scale, (view.z + view.span - float(z)) * scale


def region_number(x, z):
    px = int((float(x) - X_MIN) / CELL_LY)
    pz = int((float(z) - Z_MIN) / CELL_LY)
    if px < 0 or pz < 0 or px >= GRID or pz >= GRID:
        return 0
    return grid()[pz][px]


def region_name(x, z):
    number = region_number(x, z)
    return regions[number] if number else None


def region_colour(number):
    """A dim, distinct colour for each region (so the borders and the route stand out on top)."""
    if not number:
        return OUTSIDE
    hue = (number * 0.61803398875) % 1.0
    return _hsv(hue, 0.42, 0.30 + 0.07 * (number % 3))


def _hsv(h, s, v):
    i = int(h * 6.0) % 6
    f = h * 6.0 - int(h * 6.0)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    r, g, b = ((v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q))[i]
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


def background(view, size):
    """size rows of size '#rrggbb' strings: each pixel is coloured by its region, with a light line along region borders."""
    rows = grid()
    ids = []
    for py in range(size):
        z = view.z + view.span - (py + 0.5) * view.span / size
        pz = int((z - Z_MIN) / CELL_LY)
        line = []
        for px in range(size):
            x = view.x + (px + 0.5) * view.span / size
            cx = int((x - X_MIN) / CELL_LY)
            line.append(rows[pz][cx] if 0 <= pz < GRID and 0 <= cx < GRID else 0)
        ids.append(line)
    colours = {}
    out = []
    for py in range(size):
        line = []
        for px in range(size):
            number = ids[py][px]
            border = ((px + 1 < size and ids[py][px + 1] != number) or (py + 1 < size and ids[py + 1][px] != number))
            key = (number, border)
            if key not in colours:
                colours[key] = EDGE if border and number else region_colour(number)
            line.append(colours[key])
        out.append(line)
    return out


# ---- the route ----
def route_points(waypoints):
    """Waypoints that have a position, in order: [{system, x, y, z, neutron, index}]. 'index' is its place in the full list."""
    out = []
    for index, waypoint in enumerate(waypoints or []):
        if has_position(waypoint):
            out.append({"system": str(waypoint.get("system", "")), "x": float(waypoint["x"]), "y": float(waypoint["y"]),
                        "z": float(waypoint["z"]), "neutron": bool(waypoint.get("neutron")), "index": index})
    return out


def distance(a, b):
    return math.sqrt((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2 + (a["z"] - b["z"]) ** 2)


def route_stats(points):
    """Length of the whole route, the straight line from start to end, and how straight the route is (0-100)."""
    if len(points) < 2:
        return {"length": 0.0, "direct": 0.0, "straight": 100, "verdict": ""}
    length = sum(distance(points[i], points[i + 1]) for i in range(len(points) - 1))
    direct = distance(points[0], points[-1])
    straight = int(round(100.0 * direct / length)) if length > 0 else 100
    straight = max(0, min(100, straight))
    if straight >= 85:
        verdict = "Good route"
    elif straight >= 60:
        verdict = "A winding route"
    else:
        verdict = "A long way round"
    return {"length": length, "direct": direct, "straight": straight, "verdict": verdict}


def regions_along(points, limit=8):
    """Region names in the order the route passes through them (each once in a row)."""
    names = []
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        steps = max(1, int(math.hypot(b["x"] - a["x"], b["z"] - a["z"]) / CELL_LY))
        for s in range(steps + 1):
            t = s / float(steps)
            name = region_name(a["x"] + (b["x"] - a["x"]) * t, a["z"] + (b["z"] - a["z"]) * t)
            if name and (not names or names[-1] != name):
                names.append(name)
    if len(points) == 1:
        name = region_name(points[0]["x"], points[0]["z"])
        if name:
            names.append(name)
    if len(names) > limit:
        names = names[:limit - 1] + [names[-1]]
    return names


def with_commas(value):
    return "{:,}".format(int(round(value)))


# ---- the scene ----
def build_scene(waypoints, index, here, destination="", jumps_left=0, stops_left=0, size=300):
    """
    Everything the window has to draw, as plain data:
      background  size x size '#rrggbb'
      lines       [(x1, y1, x2, y2, colour, width, dash)]
      dots        [(x, y, radius, fill, outline)]
      labels      [(x, y, text, colour, anchor)]
      text        [(text, colour)]   lines for under the picture
      has_route   True when there is a route with positions
    waypoints = the follower's list (the first is where the route started), index = the waypoint you are heading for,
    here = your (x, y, z) or None.
    """
    points = route_points(waypoints)
    here_point = None
    if here is not None and len(here) == 3:
        here_point = {"x": float(here[0]), "y": float(here[1]), "z": float(here[2]), "system": "", "neutron": False, "index": -1}
    flat = [(p["x"], p["z"]) for p in points]
    if here_point is not None:
        flat.append((here_point["x"], here_point["z"]))
    view = fit_view(flat) if flat else WHOLE
    scene = {"view": view, "size": size, "background": background(view, size), "lines": [], "dots": [], "labels": [],
             "text": [], "has_route": len(points) >= 2}

    def px(point):
        return to_pixel(view, size, point["x"], point["z"])

    for name, x, z in LANDMARKS:
        cx, cy = to_pixel(view, size, x, z)
        if 6 < cx < size - 6 and 6 < cy < size - 6:
            scene["dots"].append((cx, cy, 2.5, LANDMARK, ""))
            scene["labels"].append((cx + 5, cy - 5, name, LANDMARK, "sw"))

    if len(points) >= 2:
        for i in range(len(points) - 1):
            a, b = px(points[i]), px(points[i + 1])
            flown = points[i + 1]["index"] < index
            scene["lines"].append((a[0], a[1], b[0], b[1], BEHIND if flown else AHEAD, 2, None))
        for point in points:
            cx, cy = px(point)
            flown = point["index"] < index
            colour = BEHIND if flown else (NEUTRON if point["neutron"] else FUEL)
            scene["dots"].append((cx, cy, 2.6 if flown else 3.4, colour, ""))
        goal = px(points[-1])
        scene["dots"].append((goal[0], goal[1], 6.0, "", GOAL))
        scene["dots"].append((goal[0], goal[1], 2.5, GOAL, ""))
        nxt = next((p for p in points if p["index"] >= index), None)
        if nxt is not None:
            cx, cy = px(nxt)
            scene["dots"].append((cx, cy, 6.5, "", NEUTRON if nxt["neutron"] else FUEL))
            if here_point is not None:
                hx, hy = px(here_point)
                scene["lines"].append((hx, hy, cx, cy, AHEAD, 1, (3, 3)))
    if here_point is not None:
        hx, hy = px(here_point)
        scene["dots"].append((hx, hy, 6.0, "", HERE))
        scene["dots"].append((hx, hy, 2.8, HERE, ""))

    scene["inset"] = _inset(points, here_point, view, size)

    # words under the picture
    if scene["has_route"]:
        stats = route_stats(points)
        goal_name = destination or points[-1]["system"]
        scene["text"].append(("NEUTRON ROUTE to %s" % goal_name, TEXT))
        scene["text"].append(("%d neutron stop%s, %d jump%s left" % (stops_left, "" if stops_left == 1 else "s", jumps_left,
                                                                    "" if jumps_left == 1 else "s"), MUTED))
        colour = GOOD if stats["straight"] >= 85 else (WARN if stats["straight"] >= 60 else BAD)
        scene["text"].append(("%s: %s ly, %d%% straight" % (stats["verdict"], with_commas(stats["length"]), stats["straight"]), colour))
        names = regions_along(points)
        if names:
            scene["text"].append(("Via " + " > ".join(names), MUTED))
    else:
        where = region_name(here_point["x"], here_point["z"]) if here_point is not None else None
        scene["text"].append(("No route plotted", TEXT))
        scene["text"].append(("You are in %s" % where if where else "Position not known yet", MUTED))
    return scene


def _inset(points, here_point, view, size):
    """A small picture of the WHOLE galaxy in the corner (so you always see where the route sits), with a box where the big picture is."""
    small = max(60, int(size * 0.30))
    inset = {"x": 6, "y": 6, "size": small, "background": background(WHOLE, small), "lines": [], "dots": [], "boxes": []}
    if len(points) >= 2:
        coords = [to_pixel(WHOLE, small, p["x"], p["z"]) for p in points]
        for a, b in zip(coords, coords[1:]):
            inset["lines"].append((a[0], a[1], b[0], b[1], AHEAD, 1, None))
        inset["dots"].append((coords[-1][0], coords[-1][1], 2.0, GOAL, ""))
    if here_point is not None:
        hx, hy = to_pixel(WHOLE, small, here_point["x"], here_point["z"])
        inset["dots"].append((hx, hy, 2.0, HERE, ""))
    if view is not WHOLE and view.span < GALAXY_SPAN:
        x1, y1 = to_pixel(WHOLE, small, view.x, view.z + view.span)
        x2, y2 = to_pixel(WHOLE, small, view.x + view.span, view.z)
        if x2 - x1 < 5:
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            x1, x2, y1, y2 = cx - 2.5, cx + 2.5, cy - 2.5, cy + 2.5
        inset["boxes"].append((x1, y1, x2, y2, NEUTRON))
    return inset


def test_route():
    """A sample route from Sol to Colonia for the 'show a test route map' button."""
    steps = [("Sol", 0, 0, 0, False), ("Neutron A", -900, -40, 1500, True), ("Neutron B", -2100, -90, 3400, True),
             ("Fuel Star", -3300, -150, 5600, False), ("Neutron C", -4700, -260, 8200, True),
             ("Neutron D", -6200, -420, 11500, True), ("Neutron E", -7800, -600, 14600, True),
             ("Neutron F", -8900, -800, 17300, True), ("Colonia", -9530, -910, 19808, True)]
    return [{"system": n, "x": x, "y": y, "z": z, "neutron": neutron, "jumps": 3, "distance_left": 0.0}
            for n, x, y, z, neutron in steps]
