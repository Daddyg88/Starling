"""RADAR POINTS: what the radar has shown at each settlement, merged into a short list of real positions.

For every settlement (by its MarketID) data/radar_points.json keeps:
  * the points: kind (terminal / ammo / recharge / turret), latitude, longitude, and how many times it was seen
  * the ground you have walked (12 metre squares), so a hack can ask you to cover the whole base
  * how many pictures were taken, the economy, the pad counts and her best guess at the layout
Only positions are kept, never pictures. The file is small and goes into the diagnostics zip.

Two sightings of the same kind within MERGE_METRES are the same object: the position becomes their average.
(Real data: the same terminal seen from different places agreed to about 3 metres, up to 7 at the radar's edge.)
"""
import json
import math
import os
import threading
from datetime import datetime

from core import paths
from core.logger import get_logger
from navigation.radar_read import metres_between

log = get_logger("radar_points")

MERGE_METRES = 6.0
CELL_METRES = 12.0
WEIGHT_CAP = 8                 # an old average counts for at most this many sightings, so a better view can still move it
SETTLEMENTS_MAX = 60
KINDS = ("terminal", "ammo", "recharge", "turret")


def default_path():
    return paths.DATA_DIR / "radar_points.json"


def _empty(name=None):
    return {"name": name, "economy": None, "group": None, "pads": None, "layout": None, "pictures": 0, "radius": None,
            "origin": None, "cells": [], "points": [], "done": False, "first": None, "last": None}


class PointStore:
    def __init__(self, path=None, stamp=None):
        self.path = path or default_path()
        self.stamp = stamp or (lambda: datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.data = {}
        self._lock = threading.Lock()
        self._load()

    # ---- file ----
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                self.data = {str(k): v for k, v in data.get("settlements", {}).items() if isinstance(v, dict)}
        except (OSError, ValueError, AttributeError):
            self.data = {}

    def save(self):
        with self._lock:
            try:
                keys = list(self.data)[-SETTLEMENTS_MAX:]
                temp = str(self.path) + ".tmp"
                with open(temp, "w", encoding="utf-8") as handle:
                    json.dump({"version": 1, "settlements": {k: self.data[k] for k in keys}}, handle, indent=1)
                os.replace(temp, self.path)
            except OSError:
                log.exception("Could not save the radar points")

    # ---- adding ----
    def entry(self, key, name=None):
        key = str(key)
        if key not in self.data:
            self.data[key] = _empty(name)
            self.data[key]["first"] = self.stamp()
        if name and not self.data[key].get("name"):
            self.data[key]["name"] = name
        return self.data[key]

    def describe(self, key, name=None, economy=None, group=None, pads=None, layout=None):
        """Remember what we know about the settlement itself (only fills in what is still empty, except the layout guess)."""
        e = self.entry(key, name)
        for field, value in (("economy", economy), ("group", group), ("pads", pads)):
            if value and not e.get(field):
                e[field] = value
        if layout:
            e["layout"] = layout
        return e

    def add_picture(self, key, sightings, stood, radius):
        """One radar picture. sightings = [(kind, lat, lon)], stood = (lat, lon) where you were, radius = the planet's radius in metres.
        Returns how many NEW points it added."""
        e = self.entry(key)
        e["pictures"] = int(e.get("pictures", 0)) + 1
        e["radius"] = radius
        e["last"] = self.stamp()
        if e.get("origin") is None:
            e["origin"] = [stood[0], stood[1]]
        self._cover(e, stood, radius)
        added = 0
        for kind, lat, lon in sightings:
            if kind not in KINDS:
                continue
            best, best_d = None, MERGE_METRES
            for point in e["points"]:
                if point["kind"] != kind:
                    continue
                d = metres_between((lat, lon), (point["lat"], point["lon"]), radius)
                if d < best_d:
                    best, best_d = point, d
            if best is None:
                e["points"].append({"kind": kind, "lat": lat, "lon": lon, "n": 1})
                added += 1
            else:
                weight = min(best["n"], WEIGHT_CAP)
                best["lat"] = (best["lat"] * weight + lat) / (weight + 1)
                best["lon"] = (best["lon"] * weight + lon) / (weight + 1)
                best["n"] += 1
        return added

    def _cover(self, e, stood, radius):
        origin = e["origin"]
        per_degree = math.pi / 180.0 * radius
        north = (stood[0] - origin[0]) * per_degree
        east = (stood[1] - origin[1]) * per_degree * math.cos(math.radians(origin[0]))
        cell = [int(round(north / CELL_METRES)), int(round(east / CELL_METRES))]
        if cell not in e["cells"] and len(e["cells"]) < 4000:
            e["cells"].append(cell)

    # ---- asking ----
    def get(self, key):
        return self.data.get(str(key))

    def counts(self, key):
        e = self.get(key) or _empty()
        out = {kind: 0 for kind in KINDS}
        for point in e["points"]:
            out[point["kind"]] = out.get(point["kind"], 0) + 1
        return out

    def points(self, key, kind=None):
        e = self.get(key) or _empty()
        return [p for p in e["points"] if kind is None or p["kind"] == kind]

    def terminals_metres(self, key):
        """The terminals as (east, north) in metres from the first place you stood: ready to compare with a map."""
        e = self.get(key)
        if not e or not e.get("origin") or not e.get("radius"):
            return []
        per_degree = math.pi / 180.0 * e["radius"]
        o = e["origin"]
        return [((p["lon"] - o[1]) * per_degree * math.cos(math.radians(o[0])), (p["lat"] - o[0]) * per_degree)
                for p in e["points"] if p["kind"] == "terminal"]

    def mark_done(self, key, done=True):
        self.entry(key)["done"] = bool(done)
