"""SETTLEMENT MAPS: simple wireframe maps of Odyssey settlements (where the terminals, locked doors, power regulator and alarm
console are), shown as a see-through drawing on top of the game. No window code here, so it can be tested.

The maps are small JSON files in maps/settlements/ (credit: CMDR Quizengine's Odyssey Map Guide, see CREDITS.md there).
A map file has: id, name, group, size [width, height], credit, buildings [{rect} or {poly}], optional pictured (true: the 'ground' outline came from a picture, so the buildings and circles are kept for the data but not drawn), pads {Small, Medium, Large} (the game's LandingPads counts, or null if not known), circles [{x, y, r}], labels [{text, x, y}],
ground [[[x, y]...]...] (optional: dim outlines of walls and pads traced from the guide's picture, drawn under everything else),
markers [{type, x, y, level}] and tips. Types: terminal_l0, terminal_above, airlock, door, power, alarm, tip.
"""
import cmath
import json
import math
import re
from pathlib import Path

from core import paths
from core.logger import get_logger

log = get_logger("settlement_maps")

GROUPS = {"tourist": "Tourist", "agriculture": "Agriculture", "agricultural": "Agriculture", "military": "Military", "industrial": "Industrial",
          "extraction": "Extraction", "high tech": "High Tech", "hightech": "High Tech", "high-tech": "High Tech"}
NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
COLOURS = {"ground": "#7a4a14", "ground_picture": "#c9741a", "building": "#ff8c1a", "label": "#ffb84d", "terminal_l0": "#c6ff00", "terminal_above": "#3da5ff", "airlock": "#ff3b3b",
           "door": "#2f6bff", "power": "#ffd42a", "alarm": "#ffd42a", "tip": "#7fd0ff"}
LETTERS = {"power": "P", "alarm": "A", "tip": "i", "terminal_l0": "T", "terminal_above": "T"}


def maps_folder():
    return paths.ROOT / "maps" / "settlements"


class SettlementMaps:
    def __init__(self, folder=None):
        self.folder = Path(folder) if folder else maps_folder()
        self.maps = {}
        self.load()

    def load(self):
        self.maps = {}
        try:
            files = sorted(self.folder.glob("*.json"))
        except OSError:
            files = []
        for path in files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("id") and isinstance(data.get("size"), list) and len(data["size"]) == 2:
                    self.maps[str(data["id"])] = data
            except (OSError, ValueError):
                log.warning("Could not read the settlement map %s", path.name)
        return len(self.maps)

    def get(self, map_id):
        return self.maps.get(str(map_id))

    def find(self, text):
        """'tourist one' / 'tourist 1' / 'high tech 3' -> the map, or None."""
        said = re.sub(r"[^a-z0-9 ]", " ", str(text or "").lower())
        said = re.sub(r"\s+", " ", said).strip()
        group = next((GROUPS[name] for name in sorted(GROUPS, key=len, reverse=True) if name in said), None)
        number = next((int(w) for w in said.split() if w.isdigit()), None) or next((NUMBERS[w] for w in said.split() if w in NUMBERS), None)
        if group is None:
            return None
        matches = [m for m in self.maps.values() if m.get("group") == group]
        if number is None:
            return matches[0] if len(matches) == 1 else None
        wanted = "%s_%d" % (group.lower().replace(" ", "_"), number)
        return self.maps.get(wanted)

    def names(self):
        return sorted(m.get("name", m["id"]) for m in self.maps.values())


class MapView:
    """Which map is on the screen right now (None = nothing). The voice command sets it, the overlay reads it."""
    def __init__(self):
        self.current = None
        self.shown_at = 0.0
        self.position = None        # {"x", "y", "angle", "heading"} in map units: where you are on the map (navigation/settlement_track.py)
        self.turn = None            # degrees: how far the drawing is turned so that north is at the top (None = drawn as the picture is)
        self.target = None          # {"x", "y", "label"}: the thing the arrow points at ("find the power plant")


def bounds(data):
    """(left, top, right, bottom) of what the map shows. Normally the picture (0, 0, width, height); a map whose landing pad is cut off by the
    picture lists "bounds" that reach past the edge so the rest of the pad can be drawn there."""
    try:
        x0, y0, x1, y1 = (float(v) for v in data["bounds"])
        if x1 > x0 and y1 > y0 and x0 <= 0 and y0 <= 0 and x1 >= float(data["size"][0]) and y1 >= float(data["size"][1]):
            return x0, y0, x1, y1
    except (KeyError, TypeError, ValueError):
        pass
    return 0.0, 0.0, float(data["size"][0]), float(data["size"][1])


PAD_METRES = {"Large": (213.0, 128.0), "Medium": (150.0, 90.0), "Small": (66.0, 55.0)}      # length x width (Elite Dangerous Wiki, Landing Pad)


def pad_corners(pad, default_scale=0.325):
    """The four corners (map units, y down) of one landing pad: a rectangle of the wiki's size for its 'size' (metres, turned into map units with the
    map's own 'scale'), its long side along 'facing' (degrees clockwise from the top of the map). Old entries with 'half' are squares."""
    cx, cy, turn = float(pad["x"]), float(pad["y"]), math.radians(float(pad.get("facing", 0)))
    if "half" in pad:
        along = across = float(pad["half"])
    else:
        length, width = PAD_METRES[str(pad["size"])]
        scale = float(pad.get("scale") or default_scale)
        along, across = length / 2.0 / scale, width / 2.0 / scale
    ux, uy = math.sin(turn), -math.cos(turn)               # along the way the ship faces
    vx, vy = math.cos(turn), math.sin(turn)                # across it
    return [(cx + ux * a + vx * b, cy + uy * a + vy * b) for a, b in ((along, -across), (along, across), (-along, across), (-along, -across))]


def pad_outline_pieces(data, step=8.0):
    """The part of each cut-off landing pad that lies OUTSIDE the picture, as short line pieces [(x1, y1, x2, y2)] (data["pad_outlines"]; the
    picture itself shows the rest of the pad), kept inside the map's bounds."""
    mw, mh = float(data["size"][0]), float(data["size"][1])
    bx0, by0, bx1, by1 = bounds(data)
    pieces = []
    for pad in data.get("pad_outlines", []) or []:
        try:
            points = pad_corners(pad, float(data.get("scale") or 0.325))
        except (KeyError, TypeError, ValueError):
            continue
        for i in range(4):
            (ax, ay), (bx, by) = points[i], points[(i + 1) % 4]
            count = max(1, int(math.hypot(bx - ax, by - ay) / step))
            for k in range(count):
                x1, y1 = ax + (bx - ax) * k / count, ay + (by - ay) * k / count
                x2, y2 = ax + (bx - ax) * (k + 1) / count, ay + (by - ay) * (k + 1) / count
                mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
                if not (0 <= mx <= mw and 0 <= my <= mh) and bx0 <= mx <= bx1 and by0 <= my <= by1:
                    pieces.append((x1, y1, x2, y2))
    return pieces


def turned_size(data, turn):
    """The width and height of the map once it is turned by `turn` degrees (None = not turned)."""
    x0, y0, x1, y1 = bounds(data)
    mw, mh = x1 - x0, y1 - y0
    if not turn:
        return mw, mh
    c, s = abs(math.cos(math.radians(turn))), abs(math.sin(math.radians(turn)))
    return mw * c + mh * s, mw * s + mh * c


def projector(data, width, height, turn=None):
    """Returns (project, scale): project(x, y) turns a point on the map picture into a pixel in a box of width x height.
    `turn` (degrees, anticlockwise as the compass sees it) is what puts north at the top: the picture is turned about its middle."""
    x0, y0, x1, y1 = bounds(data)
    tw, th = turned_size(data, turn)
    scale = min(width / tw, height / th)
    spin = cmath.exp(1j * math.radians(turn)) if turn else 1
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0

    def project(x, y):
        z = complex(float(x) - cx, -(float(y) - cy)) * spin
        return width / 2.0 + z.real * scale, height / 2.0 - z.imag * scale
    return project, scale


def layout(data, width, height, turn=None):
    """Scales a map to a box of width x height pixels (keeping its shape; `turn` degrees puts north at the top). Returns what to draw:
    {"size": (w, h), "lines": [(x1, y1, x2, y2)...], "ground": [(x1, y1, x2, y2)...], "circles": [(x, y, r)...], "labels": [(text, x, y)...],
     "markers": [(x, y, colour, text)...], "credit": str, "project": function}"""
    px, scale = projector(data, width, height, turn)
    bx0, by0, bx1, by1 = bounds(data)
    ox, oy = (width - (bx1 - bx0) * scale) / 2.0, (height - (by1 - by0) * scale) / 2.0      # (only right when not turned)
    lines, circles, labels, markers, ground = [], [], [], [], []
    for x1, y1, x2, y2 in pad_outline_pieces(data):          # the rest of a landing pad that the picture cuts off
        (a, b), (c, d) = px(x1, y1), px(x2, y2)
        ground.append((a, b, c, d))
    for outline in data.get("ground", []) or []:
        points = [px(x, y) for x, y in outline]
        if len(points) >= 3:
            ground += [(points[i][0], points[i][1], points[(i + 1) % len(points)][0], points[(i + 1) % len(points)][1]) for i in range(len(points))]
    pictured = bool(data.get("pictured"))       # the outline is drawn from a picture of the real layout: the hand-drawn boxes and circles are not drawn
    for building in ([] if pictured else data.get("buildings", [])):
        if "poly" in building:
            points = [px(x, y) for x, y in building["poly"]]
            lines += [(points[i][0], points[i][1], points[(i + 1) % len(points)][0], points[(i + 1) % len(points)][1]) for i in range(len(points))]
            continue
        x1, y1, x2, y2 = building["rect"]
        (a, b), (c, d) = px(x1, y1), px(x2, y2)
        lines += [(a, b, c, b), (c, b, c, d), (c, d, a, d), (a, d, a, b)]
    for circle in ([] if pictured else data.get("circles", [])):
        x, y = px(circle["x"], circle["y"])
        circles.append((x, y, float(circle["r"]) * scale))
    for label in data.get("labels", []):
        x, y = px(label["x"], label["y"])
        labels.append((str(label["text"]), x, y))
    for marker in data.get("markers", []):
        kind = str(marker.get("type"))
        x, y = px(marker["x"], marker["y"])
        text = LETTERS.get(kind) or ("" if marker.get("level") is None else str(marker["level"]) + ("^" if marker.get("up") else ""))
        markers.append((x, y, COLOURS.get(kind, "#ffffff"), text))
    return {"size": (width, height), "scale": scale, "offset": (ox, oy), "project": px, "lines": lines, "ground": ground, "circles": circles, "labels": labels, "markers": markers,
            "pictured": pictured, "credit": str(data.get("credit") or "")}
