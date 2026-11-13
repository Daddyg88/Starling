"""SETTLEMENT TRACKING: works out which settlement map belongs to the settlement you are at, how that map sits on the planet, and where
you are on it. No window code, so it can be tested.

How it knows (all learned from real visits, see settlement_recorder.py):
  * the GROUP comes from the journal's StationEconomy (Industrial, Agriculture...), the PADS from LandingPads (how many Small / Medium /
    Large). A map whose group and pad counts match is the suggestion; if two match she cannot choose and you say which.
  * the way the map sits (its turn and size) comes from named spots you mark by voice: "mark spot power regulator", "mark spot alarm
    console". Two spots are enough; the ship's own pad is used too when the map has a single pad and it agrees. Saved per settlement
    (data/settlement_calibration.json), so you only do it once.
  * after that every Status.json reading becomes a point and a direction on the map.
Positions on the map are in the map file's own units (pixels of the original picture).
"""
import cmath
import json
import math
import os
import re
import time

from core import paths
from core.logger import get_logger
from navigation import settlement_share, settlement_solve

log = get_logger("settlement_track")

GROUP_OF_ECONOMY = {"$economy_agri;": "Agriculture", "$economy_industrial;": "Industrial", "$economy_extraction;": "Extraction",
                    "$economy_military;": "Military", "$economy_tourism;": "Tourist", "$economy_hightech;": "High Tech"}
MIN_APART_METRES = 20.0
METRES_PER_UNIT = (0.15, 0.8)        # a sensible size for a map unit (the maps are about 1600 units wide; settlements 250-600 m)
MAX_PAD_ERROR_METRES = 12.0
FORGET_AFTER_METRES = 2500.0
SHOW_WITHIN_METRES = 700.0           # the map pops up when you are on foot this close to the settlement
ARRIVED_METRES = 6.0                 # the arrow goes away when you are this close to what it points at
DOCK_TRUST_UNITS = 50.0              # a line-up made from the landing alone is looser (the ship's heading wobbles 5 to 8 degrees), so a stop fits within this
TRUST_UNITS = 30.0                   # a later stop this close (map units, about 10 m) to a terminal, the power regulator or the alarm fits the line-up
SAME_SPOT_METRES = 6.0               # two spots of the same kind closer than this are one spot
DWELL_SECONDS = 6.0                  # standing still this long on foot = using a terminal (real visits: 6-10 s at each terminal)
STILL_METRES = 2.5
GOT_OUT_METRES = 15.0                # standing still this close to where you stepped out of the ship does not count
_FIND = re.compile(r"\b(?:where is|where s|where are|find|locate|point|show me|take me to|guide me to|lead me to|navigate to|direct me to|nearest|closest|which way)\b")
_STOP = re.compile(r"\b(?:stop|clear|remove|hide|cancel|turn off|switch off)\b.*\b(?:arrow|pointing|pointer|guiding|guide)\b")
# what you can ask the arrow for: (words, kind, name to say)
_TARGETS = (
    (re.compile(r"\b(?:power plant|power regulator|power station|power|generator|regulator)\b"), "power", "power regulator"),
    (re.compile(r"\b(?:alarm|alarms|alarm console)\b"), "alarm", "alarm console"),
    (re.compile(r"\b(?:terminal|terminals|kiosk)\b"), "terminal", "terminal"),
    (re.compile(r"\b(?:airlock|air lock|airlocks)\b"), "airlock", "airlock"),
    (re.compile(r"\b(?:door|doors|locked door)\b"), "door", "locked door"),
    (re.compile(r"\b(?:ship|my ship|pad|landing pad)\b"), "ship", "ship"),
)
_RESET = re.compile(r"\b(?:reset|forget|redo)\b.*\bsettlement\b.*\b(?:map|calibration|maps)\b")


def known_settlements():
    """MarketID -> map id for settlements whose layout is certain (maps/known_settlements.json)."""
    try:
        with open(paths.ROOT / "maps" / "known_settlements.json", encoding="utf-8") as handle:
            data = json.load(handle)
        return {str(k): str(v) for k, v in data.items() if not str(k).startswith("_")}
    except (OSError, ValueError, AttributeError):
        return {}


def known_calibrations():
    """MarketID -> saved line-up that ships with the app (maps/known_calibrations.json)."""
    try:
        with open(paths.ROOT / "maps" / "known_calibrations.json", encoding="utf-8") as handle:
            data = json.load(handle)
        return {str(k): v for k, v in data.items()
                if not str(k).startswith("_") and settlement_share.problem(v) is None}      # a bad entry is skipped, never trusted
    except (OSError, ValueError, AttributeError):
        return {}


def default_path():
    return paths.DATA_DIR / "settlement_calibration.json"


FRAME_SCALE = 0.325                  # metres per map unit (every real line-up so far)


def known_frames():
    """Map id -> how that map picture sits against the settlement's own frame (maps/map_frames.json): where the reference point is on the
    picture (origin, map units), and offset (degrees): the map's turn plus the ship's heading on pad 1. Measured from real line-ups."""
    try:
        with open(paths.ROOT / "maps" / "map_frames.json", encoding="utf-8") as handle:
            data = json.load(handle)
        return {str(k): v for k, v in data.items() if not str(k).startswith("_") and frame_problem(v) is None}
    except (OSError, ValueError, AttributeError):
        return {}


def frame_problem(frame):
    """None when a frame entry is usable, else why not (never trust a hand-edited or shared file blindly)."""
    try:
        ox, oy = frame["origin"]
        offset = float(frame["offset"])
        scale = float(frame.get("scale") or FRAME_SCALE)
        if not all(math.isfinite(float(v)) for v in (ox, oy, offset, scale)):
            return "not numbers"
        if not (-20000 <= float(ox) <= 20000 and -20000 <= float(oy) <= 20000):
            return "origin outside any map"
        if not (-360 <= offset <= 360):
            return "offset is not degrees"
        if not (METRES_PER_UNIT[0] <= scale <= METRES_PER_UNIT[1]):
            return "wrong size"
    except (KeyError, TypeError, ValueError):
        return "incomplete"
    return None


def frame_calibration(map_id, frame, heading, ref_lat, ref_lon, radius, name=None):
    """The map's line-up worked out from nothing but the ship's heading on pad 1 (the layout is turned the way pad 1 faces)."""
    scale = float(frame.get("scale") or FRAME_SCALE)
    a = cmath.rect(scale, math.radians(float(frame["offset"]) - float(heading)))
    ox, oy = frame["origin"]
    t = -a * complex(float(ox), -float(oy))
    return Calibration(map_id, a, t, ref_lat, ref_lon, radius, {"name": name, "n": 0, "err": 0.0, "how": "dock"})


def cmath_phase(z):
    return math.atan2(z.imag, z.real)


def world_xy(lat, lon, ref_lat, ref_lon, radius):
    """Metres east and north of the reference point."""
    k = radius * math.pi / 180.0
    return (lon - ref_lon) * k * math.cos(math.radians(ref_lat)), (lat - ref_lat) * k


def map_points(data):
    """The named spots a map has: power regulator, alarm console and (when it has exactly one landing pad) the pad's centre."""
    found = {}
    for marker in data.get("markers", []):
        kind = marker.get("type")
        if kind == "power" and "power" not in found:
            found["power"] = (float(marker["x"]), float(marker["y"]))
        elif kind == "alarm" and "alarm" not in found:
            found["alarm"] = (float(marker["x"]), float(marker["y"]))
    centres = {(round(float(c["x"])), round(float(c["y"]))) for c in data.get("circles", [])}
    pads = data.get("pads")
    if len(centres) == 1 and pads and sum(int(v or 0) for v in pads.values()) == 1:
        found["pad"] = (float(data["circles"][0]["x"]), float(data["circles"][0]["y"]))
    return found


def feature_of(label):
    said = str(label or "").lower()
    if "power" in said:
        return "power"
    if "alarm" in said:
        return "alarm"
    if said.strip() in ("pad", "landing pad", "my pad", "the pad"):
        return "pad"
    if "terminal" in said or "kiosk" in said:
        return "terminal"
    if any(word in said for word in ("door", "airlock", "air lock", "entrance")):
        return "entry"
    return None


def fit(pairs):
    """pairs: [((map_x, map_y_down), (east, north))...]. Returns (a, t, rms metres): world = a * map + t, with the map drawn y UP."""
    z = [complex(p[0], -p[1]) for p, _ in pairs]
    w = [complex(q[0], q[1]) for _, q in pairs]
    zc, wc = sum(z) / len(z), sum(w) / len(w)
    num = sum((zi - zc).conjugate() * (wi - wc) for zi, wi in zip(z, w))
    den = sum(abs(zi - zc) ** 2 for zi in z)
    a = num / den
    t = wc - a * zc
    rms = math.sqrt(sum(abs(wi - (a * zi + t)) ** 2 for zi, wi in zip(z, w)) / len(z))
    return a, t, rms


class Calibration:
    def __init__(self, map_id, a, t, ref_lat, ref_lon, radius, meta=None):
        self.map_id, self.a, self.t = map_id, complex(a), complex(t)
        self.ref_lat, self.ref_lon, self.radius = ref_lat, ref_lon, radius
        self.meta = dict(meta or {})        # name, n (places stood at), err (average miss, map units), how: for sharing (navigation/settlement_share.py)

    def to_map(self, lat, lon):
        east, north = world_xy(lat, lon, self.ref_lat, self.ref_lon, self.radius)
        z = (complex(east, north) - self.t) / self.a
        return z.real, -z.imag

    def from_world(self, east, north):
        """A place given as metres east and north of the reference point, as a point on the map."""
        z = (complex(east, north) - self.t) / self.a
        return z.real, -z.imag

    def turn_degrees(self):
        """How far to turn the map picture so that north is at the top."""
        return math.degrees(math.atan2(self.a.imag, self.a.real))

    def arrow_angle(self, heading):
        """Degrees clockwise from the top of the map for a game heading (0 = north, clockwise)."""
        h = math.radians(float(heading))
        u = complex(math.sin(h), math.cos(h)) / self.a
        return math.degrees(math.atan2(u.real, u.imag)) % 360.0

    def to_json(self):
        out = {"v": 2, "map": self.map_id, "a": [self.a.real, self.a.imag], "t": [self.t.real, self.t.imag],
               "ref": [self.ref_lat, self.ref_lon], "radius": self.radius}
        out.update({k: v for k, v in self.meta.items() if k in ("name", "n", "err", "how")})
        return out

    @classmethod
    def from_json(cls, data):
        return cls(data["map"], complex(*data["a"]), complex(*data["t"]), data["ref"][0], data["ref"][1], data["radius"],
                   {k: data[k] for k in ("name", "n", "err", "how") if k in data})


class SettlementTracker:
    def __init__(self, state_provider, maps, view, path=None):
        self.state_provider, self.maps, self.view = state_provider, maps, view
        self.path = path or default_path()
        self.settlement = None          # what the journal said about the settlement you are at
        self.anchors = {}               # feature -> (east, north) metres from the settlement's reference point
        self.spots = []                 # [(kind, east, north)] every place you stood at that the map can match (terminals, power...)
        self.calibration = None
        self.provisional = False        # lined up from only three stops: the next stops check it (see _check_stop)
        self.checks = [0, 0]            # [stops that fit the line-up, stops that did not]
        self.dismissed = False          # you said "hide the settlement map": it stays hidden until the next settlement
        self._was_on_foot = False
        self._still = None              # (east, north, since, counted): where you have been standing
        self._foot_start = None
        self.clock = time.monotonic
        self.say = None                 # (text) -> speaks a sentence; set by the app (voice helpers' answers are not spoken by themselves)
        self._asked = False
        self.known = known_settlements()
        self.shipped = known_calibrations()
        self.frames = known_frames()           # map id -> frame: shipped ones, then the ones learned from your own line-ups
        self.frames_path = str(self.path) + ".frames"
        self._load_frames()
        self.layout_hint = None         # (market) -> a map id found by a finished base hack (navigation/hack.py), or None
        self.auto_shown = False         # the map on screen was put there by this tracker (so this tracker may take it down)
        self.saved = {}
        self._load()

    # ---- file ----
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
            self.saved = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            self.saved = {}

    def _load_frames(self):
        try:
            with open(self.frames_path, encoding="utf-8") as handle:
                data = json.load(handle)
            for key, value in (data.items() if isinstance(data, dict) else []):
                if frame_problem(value) is None:
                    self.frames[str(key)] = value
        except (OSError, ValueError):
            pass

    def _save_frames(self):
        try:
            learned = {k: v for k, v in self.frames.items() if v.get("learned")}
            temp = self.frames_path + ".tmp"
            with open(temp, "w", encoding="utf-8") as handle:
                json.dump(learned, handle, indent=1)
            os.replace(temp, self.frames_path)
        except OSError:
            log.exception("Could not save the settlement frames")

    def _save(self):
        try:
            temp = str(self.path) + ".tmp"
            with open(temp, "w", encoding="utf-8") as handle:
                json.dump(self.saved, handle, indent=1)
            os.replace(temp, self.path)
        except OSError:
            log.exception("Could not save the settlement calibration")

    # ---- journal ----
    def on_entry(self, entry, silent=False):
        """`silent` lines are the journal being caught up after Starling started: they still tell us which settlement you are at
        (so starting her after you arrived works), but not where the ship is now."""
        if not isinstance(entry, dict):
            return
        name = entry.get("event")
        try:
            if name == "ApproachSettlement" and entry.get("Latitude") is not None:
                self._approach(entry)
            elif name in ("SupercruiseEntry", "FSDJump", "Shutdown"):
                self._leave()
            elif self.settlement is not None:
                if name == "DockingGranted" and entry.get("LandingPad") is not None:
                    self.settlement["pad_number"] = entry.get("LandingPad")
                if name in ("DockingRequested", "Docked") and "LandingPads" in entry:
                    self.settlement["pads"] = {k: int(entry["LandingPads"].get(k, 0) or 0) for k in ("Small", "Medium", "Large")}
                    self._choose()
                if name in ("Docked", "Touchdown") and not silent:
                    self._ship_landed()
        except Exception:
            log.exception("The settlement tracker could not handle %s", name)

    def _approach(self, entry):
        economy = str(entry.get("StationEconomy") or "").lower()
        market = str(entry.get("MarketID") or entry.get("Name") or "")
        self.settlement = {"name": entry.get("Name"), "market": market, "group": GROUP_OF_ECONOMY.get(economy), "pads": None,
                           "lat": float(entry["Latitude"]), "lon": float(entry["Longitude"]), "radius": None, "map": None}
        self.anchors = {}
        self.spots = []
        self.calibration = None
        self.dismissed = False
        self._asked = False
        self.view.position = None
        if self.known.get(market) and self.maps.get(self.known[market]) is not None:
            self.settlement["map"] = self.known[market]
        if not self.settlement["map"] and self.layout_hint is not None:
            try:
                self.adopt_layout(self.layout_hint(market), market)       # an earlier hack of this very base found its layout
            except Exception:
                log.exception("The settlement layout hint failed")
        known = self.saved.get(market)
        if isinstance(known, dict) and known.get("disabled"):
            known = None                       # you said "reset settlement map" here: neither your old line-up nor the shipped one
        else:
            if known is not None and known.get("v") != 2:
                known = None                   # saved by an older, less careful line-up: not trusted
            known = known or self.shipped.get(market)
        if known:
            try:
                self.calibration = Calibration.from_json(known)
                self.settlement["map"] = known["map"]
                self.provisional = known.get("how") == "stops" and int(known.get("n") or 0) <= settlement_solve.MIN_SPOTS_LOCKED
                self.checks = [0, 0]
                log.info("Settlement %s: map %s, calibration remembered", self.settlement["name"], known["map"])
            except (KeyError, TypeError, ValueError, IndexError):
                self.calibration = None

    def _leave(self):
        self.settlement, self.anchors, self.calibration, self.spots = None, {}, None, []
        self.provisional, self.checks = False, [0, 0]
        self.view.position = None
        if self.auto_shown:
            self.view.current = None
        self.auto_shown = False

    def _choose(self):
        """Group + pad counts: when exactly one map matches it is the suggestion."""
        s = self.settlement
        if s is None or s.get("map"):
            return
        candidates = self.candidates()
        if len(candidates) == 1:
            s["map"] = candidates[0]["id"]
            log.info("Settlement %s looks like %s (group %s, pads %s)", s["name"], s["map"], s["group"], s["pads"])

    def adopt_layout(self, map_id, market=None):
        """A finished base hack worked out which layout this base is (the radar's terminals fit it clearly better than the others): use it, so the map
        comes up. Only when no map is chosen yet, the base is the same one, and the map exists. Returns True when it was taken."""
        s = self.settlement
        if s is None or s.get("map") or not map_id or self.maps.get(map_id) is None:
            return False
        if market is not None and str(market) != str(s.get("market")):
            return False
        s["map"] = map_id
        log.info("Settlement %s: layout %s taken from the base hack", s.get("name"), map_id)
        return True

    def candidates(self):
        s = self.settlement
        if s is None or not s.get("group"):
            return []
        found = []
        for data in self.maps.maps.values():
            if data.get("group") != s["group"]:
                continue
            pads = data.get("pads")
            if s.get("pads") is not None and pads is not None and {k: int(pads.get(k, 0) or 0) for k in ("Small", "Medium", "Large")} != s["pads"]:
                continue
            found.append(data)
        return found

    def _speak(self, text):
        if self.say is not None and text:
            try:
                self.say(text)
            except Exception:
                log.exception("The settlement tracker could not speak")

    def set_dismissed(self, value):
        """The voice command hid (True) or showed (False) the map by hand: the tracker must not fight that."""
        self.dismissed = bool(value)
        self.auto_shown = False
        if value:
            self.view.target = None
        elif self.settlement is not None and not self.settlement.get("map") and self.view.current:
            self.settlement["map"] = self.view.current              # you named the layout: from now on this is the one

    def options(self):
        """The names of the layouts it could be (group and pad counts match), for 'show settlement map' when she cannot choose."""
        return sorted(str(d.get("name", d["id"])) for d in self.candidates())

    def suggestion(self):
        """The map id for the settlement you are at, or None."""
        if self.settlement is None:
            return None
        return self.settlement.get("map")

    def _ship_landed(self):
        state = self.state_provider()
        if state is None or getattr(state, "latitude", None) is None or self.settlement is None:
            return
        self.settlement["radius"] = state.planet_radius
        self.anchors["pad"] = world_xy(state.latitude, state.longitude, self.settlement["lat"], self.settlement["lon"], state.planet_radius)
        self._add_spot("pad", self.anchors["pad"])
        heading = getattr(state, "heading", None)
        if heading is not None:
            self.settlement["dock_heading"] = float(heading)
            self._dock_line_up()

    def _dock_line_up(self):
        """On pad 1 the ship faces the way the whole layout is turned. When this layout's frame is known (from an earlier line-up of the same
        layout, here or at another settlement) the map can be lined up from the landing alone, then the next stops check it."""
        s = self.settlement
        if self.calibration is not None or s is None or s.get("dock_rejected") or str(s.get("pad_number")) != "1":
            return
        map_id = s.get("map")
        frame = self.frames.get(map_id) if map_id else None
        if frame is None or not s.get("radius") or s.get("dock_heading") is None:
            return
        self.calibration = frame_calibration(map_id, frame, s["dock_heading"], s["lat"], s["lon"], s["radius"], s.get("name"))
        self.provisional, self.checks = True, [0, 0]
        self.view.current = self.view.current or map_id
        log.info("Settlement map %s lined up from the landing (ship heading %.0f on pad 1): the next stops will check it", map_id, s["dock_heading"])
        self._speak("I have lined up the map from the way you landed. I will check it as you walk to the terminals.")

    def _remember_frame(self):
        """A line-up worth trusting also teaches the layout's frame, so the next settlement with this layout can be lined up from the landing."""
        s, cal = self.settlement, self.calibration
        if s is None or cal is None or cal.meta.get("how") == "dock" or s.get("dock_heading") is None or str(s.get("pad_number")) != "1":
            return
        if abs(cal.a) == 0:
            return
        z = -cal.t / cal.a
        offset = (self.calibration.turn_degrees() + s["dock_heading"] + 180.0) % 360.0 - 180.0
        new = {"origin": [round(z.real, 1), round(-z.imag, 1)], "offset": round(offset, 1), "scale": round(abs(cal.a), 4),
               "learned": True, "n": 1}
        old = self.frames.get(cal.map_id)
        if old and old.get("learned") and old.get("n"):
            n = min(int(old["n"]), 9)               # a running average: later line-ups count a little less each time
            mix = lambda a, b: (a * n + b) / (n + 1)
            diff = (offset - float(old["offset"]) + 180.0) % 360.0 - 180.0
            new = {"origin": [round(mix(float(old["origin"][0]), z.real), 1), round(mix(float(old["origin"][1]), -z.imag), 1)],
                   "offset": round(float(old["offset"]) + diff / (n + 1), 1), "scale": round(mix(float(old.get("scale") or FRAME_SCALE), abs(cal.a)), 4),
                   "learned": True, "n": n + 1}
        if frame_problem(new) is None:
            self.frames[cal.map_id] = new
            self._save_frames()

    # ---- marking spots ----
    def on_mark(self, label, here):
        """Called when you mark a spot. Returns an extra sentence (or None)."""
        feature = feature_of(label)
        s = self.settlement
        if feature is None or s is None or here is None:
            return None
        radius = here.get("radius") or s.get("radius")
        if not radius:
            return None
        s["radius"] = radius
        point = world_xy(here["lat"], here["lon"], s["lat"], s["lon"], radius)
        self.anchors[feature] = point
        self._add_spot(feature, point)
        return self._line_up()

    def _add_spot(self, kind, point):
        for other, east, north in self.spots:
            if other == kind and math.hypot(east - point[0], north - point[1]) < SAME_SPOT_METRES:
                return False
        self.spots.append((kind, point[0], point[1]))
        del self.spots[:-40]
        return True

    def _line_up(self, speak=True):
        """Tries to line the map up with the spots so far. Returns a sentence for the marking command (or None)."""
        s = self.settlement
        if s is None or self.calibration is not None:
            return None
        map_id = s.get("map") or self.view.current
        if "power" in self.anchors and "alarm" in self.anchors and map_id:
            done = self._calibrate(map_id)                         # the two-spot way, as before
            if done:
                return done
        found = self._solve(map_id)
        if found:
            return found
        have = [f for f in ("power", "alarm") if f in self.anchors]
        if len(have) == 1 and map_id:
            return "Now mark the %s, or stand at a few terminals and mark those." % ("alarm console" if have[0] == "power" else "power regulator")
        count = len([1 for kind, _, _ in self.spots if kind != "pad"])
        if not speak:
            return None
        need = settlement_solve.MIN_SPOTS_LOCKED if map_id else settlement_solve.SPOTS_TO_CHOOSE_LOCKED
        if count < need:
            return "Stand at %d more terminals (or the power regulator, or the alarm console) and the map will line itself up." % (need - count)
        return "I cannot tell which way the map turns yet. Mark another terminal that is further away."

    def _solve(self, map_id):
        s = self.settlement
        count = len([1 for kind, _, _ in self.spots if kind != "pad"])
        # first with the map's size fixed (three stops are enough), then with any size (four or five stops)
        passes = (
            (settlement_solve.LOCKED_SCALES, settlement_solve.LOCKED_RANGE,
             settlement_solve.MIN_SPOTS_LOCKED if map_id else settlement_solve.SPOTS_TO_CHOOSE_LOCKED),
            (None, None, settlement_solve.MIN_SPOTS if map_id else settlement_solve.SPOTS_TO_CHOOSE),
        )
        for scales, scale_range, minimum in passes:
            if count < minimum:
                continue
            found = self._solve_with(map_id, scales, scale_range, minimum)
            if found:
                return found
        return None

    def _solve_with(self, map_id, scales, scale_range, minimum):
        s = self.settlement
        if map_id:
            options = [self.maps.get(map_id)]
        else:
            options = self.candidates()
        results = []
        for data in options:
            if data is None:
                continue
            result = settlement_solve.solve(data, self.spots, minimum, scales)
            if result and settlement_solve.clear(result, scale_range) and METRES_PER_UNIT[0] <= abs(result["a"]) <= METRES_PER_UNIT[1]:
                results.append((result["error"], data, result))
        if not results:
            return None
        results.sort(key=lambda row: row[0])
        if len(results) > 1 and results[1][0] < results[0][0] * 1.4 + 5.0:
            return None                                              # two layouts fit about equally: not sure which one this is
        error, data, result = results[0]
        self.calibration = Calibration(data["id"], result["a"], result["t"], s["lat"], s["lon"], s["radius"],
                                       {"name": s.get("name"), "n": result["n"], "err": round(result["error"], 1), "how": "stops"})
        s["map"] = data["id"]
        self.provisional = result["n"] <= settlement_solve.MIN_SPOTS_LOCKED
        self.checks = [0, 0]
        self.saved[s["market"]] = self.calibration.to_json()
        self._save()
        if not self.provisional:
            self._remember_frame()
        log.info("Settlement map %s lined up from %d spots (%s size): %.3f m per unit, turned %.0f degrees, average miss %.0f units",
                 data["id"], result["n"], "fixed" if scales else "free", abs(result["a"]), math.degrees(cmath_phase(result["a"])), error)
        return "Got it: this is the %s map and it is lined up. You are on it now." % data.get("name", data["id"])

    def _calibrate(self, map_id):
        data = self.maps.get(map_id)
        s = self.settlement
        if data is None or s is None or not s.get("radius"):
            return None
        points = map_points(data)
        pairs = [(points[f], self.anchors[f][:2]) for f in ("power", "alarm") if f in self.anchors and f in points]
        if len(pairs) < 2:
            return None
        if math.hypot(pairs[0][1][0] - pairs[1][1][0], pairs[0][1][1] - pairs[1][1][1]) < MIN_APART_METRES:
            return "Those two spots are too close together: stand at the power regulator and at the alarm console, which are further apart."
        a, t, rms = fit(pairs)
        if not METRES_PER_UNIT[0] <= abs(a) <= METRES_PER_UNIT[1]:
            return "That does not fit the %s map (the distances are the wrong size), so I did not use it. Say reset settlement map and try again." % data.get("name", map_id)
        note = ""
        pad = self.anchors.get("pad")
        if pad and "pad" in points:                                  # the ship's own pad as a check (not used when it disagrees)
            a3, t3, rms3 = fit(pairs + [(points["pad"], pad[:2])])
            if rms3 <= MAX_PAD_ERROR_METRES:
                a, t, note = a3, t3, " (checked against your landing pad too)"
        self.calibration = Calibration(map_id, a, t, s["lat"], s["lon"], s["radius"],
                                       {"name": s.get("name"), "n": len(pairs) + (1 if note else 0), "err": round(rms / 0.325, 1), "how": "marks"})
        s["map"] = map_id
        self.saved[s["market"]] = self.calibration.to_json()
        self._save()
        self._remember_frame()
        self.view.current = self.view.current or map_id
        log.info("Settlement map %s fitted: %.3f m per unit, turned %.0f degrees%s", map_id, abs(a), math.degrees(math.atan2(a.imag, a.real)), note)
        return "Got it: the %s map is lined up%s. You are on it now." % (data.get("name", map_id), note)

    # ---- Status.json ----
    def on_status(self, state):
        try:
            self._status(state)
        except Exception:
            log.exception("The settlement tracker could not use a position")

    def _status(self, state):
        lat = getattr(state, "latitude", None)
        s = self.settlement
        on_foot = bool(getattr(state, "status_flags2", 0) & 1)
        near = None
        if s is not None and lat is not None:
            radius = s.get("radius") or getattr(state, "planet_radius", None)
            if radius:
                east, north = world_xy(lat, state.longitude, s["lat"], s["lon"], radius)
                near = math.hypot(east, north)
                s["radius"] = radius
                self._dwell(on_foot, east, north, near)
        self._show_or_hide(on_foot, near)
        cal = self.calibration
        if cal is None or lat is None or near is None or near > FORGET_AFTER_METRES:
            self.view.position = None
            self.view.turn = None
            self.view.target = None
            return
        x, y = cal.to_map(lat, state.longitude)
        heading = getattr(state, "heading", None)
        self.view.turn = cal.turn_degrees() if self.view.current == cal.map_id else None
        angle = None
        if heading is not None:
            angle = float(heading) % 360.0 if self.view.turn is not None else cal.arrow_angle(heading)      # turned north-up: the heading is the arrow
        self.view.position = {"x": x, "y": y, "angle": angle}
        target = self.view.target
        if target is not None and math.hypot(x - target["x"], y - target["y"]) * abs(cal.a) < ARRIVED_METRES:
            self.view.target = None                               # you are there

    def _dwell(self, on_foot, east, north, near):
        """Using a terminal makes the game write nothing (no journal line, no screen number on foot: seen in real visits), but you
        STAND STILL for several seconds. Standing still on foot, away from where you got out, counts as 'I am at something'."""
        now = self.clock()
        if not on_foot or near > SHOW_WITHIN_METRES:
            self._still = None
            self._foot_start = None
            return
        if self._foot_start is None:
            self._foot_start = (east, north)
        if self._still is None or math.hypot(east - self._still[0], north - self._still[1]) > STILL_METRES:
            self._still = (east, north, now, False)
            return
        x, y, since, counted = self._still
        if counted or now - since < DWELL_SECONDS:
            return
        if self.calibration is not None:
            if self.provisional:
                self._still = (x, y, since, True)
                if math.hypot(x - self._foot_start[0], y - self._foot_start[1]) >= GOT_OUT_METRES:
                    self._check_stop(x, y)
            return
        self._still = (x, y, since, True)
        if math.hypot(x - self._foot_start[0], y - self._foot_start[1]) < GOT_OUT_METRES:
            return                                                 # just stepped out of the ship
        if self._add_spot("stop", (x, y)):
            log.info("Settlement: stood still %.0f s, %.0f m from the reference point (%d stops, not counting your ship)", now - since, near,
                     len([1 for kind, _, _ in self.spots if kind != "pad"]))
            self._line_up(speak=False)

    def _check_stop(self, east, north):
        """A line-up made from only three stops is checked by the stops that follow: a terminal (or the power regulator, or the alarm) should
        be where the map says. Suit recharges and other stops that are not on the map do not count against it more than twice."""
        cal, data = self.calibration, self.maps.get(self.calibration.map_id)
        if data is None:
            return
        x, y = cal.from_world(east, north)
        near = min((math.hypot(x - u, y - v) for u, v in settlement_solve.features(data)["stop"]), default=1e9)
        if near <= (DOCK_TRUST_UNITS if cal.meta.get("how") == "dock" else TRUST_UNITS):
            self.checks[0] += 1
            if self.checks[0] >= 2:
                self.provisional = False                           # two later stops agree: it is right
                if cal.meta.get("how") == "dock" and self.settlement is not None:
                    self.saved[self.settlement["market"]] = cal.to_json()       # a landing-only line-up the walk has proved: keep it
                    self._save()
                else:
                    self._remember_frame()
                log.info("Settlement map %s confirmed by later stops", cal.map_id)
        else:
            self.checks[1] += 1
            log.info("Settlement: a later stop is %.0f map units from any terminal (%d fit, %d do not)", near, *self.checks)
            if self.checks[1] >= 2 and self.checks[1] > self.checks[0]:
                self._take_back()

    def _take_back(self):
        """The three-stop line-up was probably wrong: forget it and start collecting stops again."""
        s = self.settlement
        log.info("Settlement map %s taken back: later stops did not fit", self.calibration.map_id)
        if s is not None:
            s["dock_rejected"] = True                              # do not line it up from the landing again at this visit
            self.saved.pop(s["market"], None)
            self._save()
            if not (self.known.get(s["market"])):
                s["map"] = None
        self.calibration, self.provisional, self.checks = None, False, [0, 0]
        self.view.position = None
        self._choose()
        if self.say is not None:
            self._speak("That map does not fit where you have been standing, so I have taken it back. Stand at a few more terminals and I will try again.")

    def _show_or_hide(self, on_foot, near):
        """The map comes up when you step out near a settlement we have a map for, and goes when you get back in or leave."""
        s = self.settlement
        want = (s is not None and not self.dismissed and on_foot and near is not None and near <= SHOW_WITHIN_METRES
                and bool(s.get("map")))
        if (s is not None and not self.dismissed and on_foot and near is not None and near <= SHOW_WITHIN_METRES and not s.get("map")
                and not self._asked and self.view.current is None):
            could = self.options()
            self._asked = True
            if 1 < len(could) < 8:
                self._speak("I cannot tell which %s layout this is: %s. Say show settlement map and the name, for example %s."
                            % (s.get("group") or "settlement", ", ".join(could), could[0].lower()))
        if want and self.view.current is None:
            self.view.current = s["map"]
            self.view.shown_at = time.monotonic()
            self.auto_shown = True
        elif want and self.view.current is not None and self.auto_shown:
            self.view.shown_at = time.monotonic()              # still here: do not let the 15 minute timer take it down
        elif not want and self.auto_shown and self.view.current is not None:
            self.view.current = None
            self.auto_shown = False
        if self.view.current is None:
            self.auto_shown = False

    # ---- voice ----
    def try_handle(self, text):
        said = re.sub(r"[^a-z ]", " ", str(text or "").lower())
        said = re.sub(r"\s+", " ", said).strip()
        pointed = self._point(said)
        if pointed is not None:
            self._speak(pointed)
            return pointed
        if not _RESET.search(said):
            return None
        s = self.settlement
        if s is not None:
            self.saved[s["market"]] = {"v": 2, "disabled": True}         # remembered, so the shipped line-up is not put straight back
            self._save()
            s["map"] = None
            self._choose()
        self.anchors, self.calibration, self.spots = {}, None, []
        self.view.position = None
        self._speak("Settlement map reset.")
        return "Settlement map reset. Walk to a few terminals and say mark spot terminal at each."

    # ---- the arrow ("find the power plant") ----
    def _on_foot(self):
        state = self.state_provider()
        return state is not None and bool(getattr(state, "status_flags2", 0) & 1)

    def _point(self, said):
        """Voice: point the arrow at something, or take it away. Only answers when you are on foot at a settlement we know."""
        if self.settlement is None or not self._on_foot():
            return None
        if _STOP.search(said) and self.view.target is not None:
            self.view.target = None
            return "Arrow off."
        if not _FIND.search(said):
            return None
        wanted = next(((kind, name) for pattern, kind, name in _TARGETS if pattern.search(said)), None)
        if wanted is None:
            return None
        kind, name = wanted
        cal, where = self.calibration, self.view.position
        if cal is None or not where:
            return "I cannot place you on the settlement map yet, so I cannot point. Open a few terminals, or say mark spot terminal at each, and I will line the map up."
        found = self._nearest(kind, where, cal)
        if found is None:
            return "I do not see a %s on this map." % name
        x, y, metres, floor = found
        label = ("nearest " if kind in ("terminal", "door", "airlock") else "") + name
        self.view.target = {"x": x, "y": y, "label": label}
        self.view.shown_at = time.monotonic()
        if self.view.current is None:
            self.view.current, self.auto_shown = cal.map_id, False
        step = cal.a * complex(x - where["x"], -(y - where["y"]))          # the way to it in metres east / north
        east, north = step.real, step.imag
        bearing = math.degrees(math.atan2(east, north)) % 360.0
        state = self.state_provider()
        heading = getattr(state, "heading", None)
        way = relative_words(bearing, heading) if heading is not None else compass_words(bearing)
        extra = ", upstairs" if floor == "up" else ""
        return "The %s is about %d metres %s%s. The arrow on the map points to it." % (label, max(1, round(metres / 5.0) * 5 if metres > 12 else round(metres)), way, extra)

    def _nearest(self, kind, where, cal):
        if kind == "ship":
            pad = self.anchors.get("pad")
            if pad is None:
                return None
            x, y = cal.from_world(pad[0], pad[1])
            return x, y, math.hypot(x - where["x"], y - where["y"]) * abs(cal.a), None
        data = self.maps.get(cal.map_id)
        if data is None:
            return None
        best = None
        for marker in data.get("markers", []):
            mtype = str(marker.get("type") or "")
            if kind == "terminal" and not mtype.startswith("terminal"):
                continue
            if kind in ("power", "alarm", "airlock", "door") and mtype != kind:
                continue
            x, y = float(marker["x"]), float(marker["y"])
            dist = math.hypot(x - where["x"], y - where["y"]) * abs(cal.a)
            if best is None or dist < best[2]:
                best = (x, y, dist, "up" if mtype == "terminal_above" else None)
        return best


def compass_words(bearing):
    names = ("north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west")
    return "to the " + names[int(((bearing % 360.0) + 22.5) // 45) % 8]


def relative_words(bearing, heading):
    """Where something is compared with the way you are facing."""
    turn = (bearing - float(heading) + 180.0) % 360.0 - 180.0
    if abs(turn) <= 25:
        return "straight ahead"
    if abs(turn) >= 155:
        return "behind you"
    side = "right" if turn > 0 else "left"
    return ("ahead and to the %s" if abs(turn) < 70 else "to the %s" if abs(turn) < 110 else "behind you and to the %s") % side
