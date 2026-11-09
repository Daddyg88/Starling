"""SETTLEMENT MAPS: simple wireframe maps of Odyssey settlements (where the terminals, locked doors, power regulator and alarm
console are), shown as a see-through drawing on top of the game. No window code here, so it can be tested.

The maps are small JSON files in maps/settlements/ (credit: CMDR Quizengine's Odyssey Map Guide, see CREDITS.md there).
A map file has: id, name, group, size [width, height], credit, buildings [{rect}], circles [{x, y, r}], labels [{text, x, y}],
markers [{type, x, y, level}] and tips. Types: terminal_l0, terminal_above, airlock, door, power, alarm, tip.
"""
import json
import re
from pathlib import Path

from core import paths
from core.logger import get_logger

log = get_logger("settlement_maps")

GROUPS = {"tourist": "Tourist", "agriculture": "Agriculture", "agricultural": "Agriculture", "military": "Military", "industrial": "Industrial",
          "extraction": "Extraction", "high tech": "High Tech", "hightech": "High Tech", "high-tech": "High Tech"}
NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
COLOURS = {"building": "#ff8c1a", "label": "#ffb84d", "terminal_l0": "#c6ff00", "terminal_above": "#3da5ff", "airlock": "#ff3b3b",
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


def layout(data, width, height):
    """Scales a map to a box of width x height pixels (keeping its shape). Returns what to draw:
    {"size": (w, h), "lines": [(x1, y1, x2, y2)...], "circles": [(x, y, r)...], "labels": [(text, x, y)...],
     "markers": [(x, y, colour, text)...], "credit": str}"""
    mw, mh = float(data["size"][0]), float(data["size"][1])
    scale = min(width / mw, height / mh)
    ox, oy = (width - mw * scale) / 2.0, (height - mh * scale) / 2.0

    def px(x, y):
        return ox + float(x) * scale, oy + float(y) * scale
    lines, circles, labels, markers = [], [], [], []
    for building in data.get("buildings", []):
        x1, y1, x2, y2 = building["rect"]
        (a, b), (c, d) = px(x1, y1), px(x2, y2)
        lines += [(a, b, c, b), (c, b, c, d), (c, d, a, d), (a, d, a, b)]
    for circle in data.get("circles", []):
        x, y = px(circle["x"], circle["y"])
        circles.append((x, y, float(circle["r"]) * scale))
    for label in data.get("labels", []):
        x, y = px(label["x"], label["y"])
        labels.append((str(label["text"]), x, y))
    for marker in data.get("markers", []):
        kind = str(marker.get("type"))
        x, y = px(marker["x"], marker["y"])
        text = LETTERS.get(kind) or ("" if marker.get("level") is None else str(marker["level"]))
        markers.append((x, y, COLOURS.get(kind, "#ffffff"), text))
    return {"size": (width, height), "lines": lines, "circles": circles, "labels": labels, "markers": markers,
            "credit": str(data.get("credit") or "")}
