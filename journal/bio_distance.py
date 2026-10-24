"""
Biology distance alert: after a biological sample she watches how far you walk, and when you are far enough from it
for the next sample she plays a beep and says so ("You're far enough away now, 100 metres. Take the next sample.").

How: the journal says a sample was taken (ScanOrganic). Status.json says where you are (latitude, longitude, planet radius)
about once a second. The distance over the surface is worked out with the haversine formula.
How far is "far enough" depends on the genus (config/exobiology_values.json: colony_distance_m).
"""

import math
import sys
import threading

from core.logger import get_logger

log = get_logger("biodistance")


def surface_distance(lat1, lon1, lat2, lon2, radius):
    """Metres between two latitude/longitude points (degrees) on a sphere of this radius (metres)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def play_beep():
    if sys.platform != "win32":
        return
    try:
        import winsound
        winsound.Beep(1100, 140)
        winsound.Beep(1500, 180)
    except Exception:
        log.exception("Beep failed")


class BioDistance:
    def __init__(self, bus, narrator, settings, state_provider, beep=None, spawn=None):
        self.bus = bus
        self.narrator = narrator
        self.settings = settings
        self.state_provider = state_provider
        self.beep = beep or play_beep
        self.spawn = spawn or self._thread
        self.anchor = None            # (latitude, longitude, radius, metres needed)

    @staticmethod
    def _thread(function):
        threading.Thread(target=function, name="bio-beep", daemon=True).start()

    def attach(self):
        self.bus.subscribe("ScanOrganic", self.on_scan)

    def detach(self):
        self.bus.unsubscribe("ScanOrganic", self.on_scan)

    def enabled(self):
        return bool(self.settings.get("exobiology.distance_alert", True) and self.settings.get("talk.exobiology", True))

    def on_scan(self, event):
        data = getattr(event, "data", None) or {}
        state = self.state_provider()
        if data.get("Complete") or state is None:
            self.anchor = None                       # three samples done: nothing more to walk away from
            return
        needed = state.exobiology.colony_distance(data)
        lat, lon, radius = state.latitude, state.longitude, state.planet_radius
        if not needed or lat is None or lon is None or not radius:
            self.anchor = None
            return
        self.anchor = (lat, lon, radius, float(needed))

    def check(self, state):
        """Called after every Status.json read. Returns True the moment she tells you."""
        if self.anchor is None:
            return False
        lat, lon = state.latitude, state.longitude
        if lat is None or lon is None:
            return False
        a_lat, a_lon, radius, needed = self.anchor
        if surface_distance(a_lat, a_lon, lat, lon, radius) < needed:
            return False
        self.anchor = None                           # once per sample
        if not self.enabled():
            return False
        if self.settings.get("exobiology.distance_beep", True):
            self.spawn(self.beep)
        self.narrator.say("BioFarEnough", {"distance": str(int(needed))})
        return True
