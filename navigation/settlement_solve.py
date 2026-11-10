"""SETTLEMENT SOLVER: works out how a settlement map is turned and where it sits, from spots you have stood at.

Every settlement is rotated differently, so the map has to be lined up. You do NOT have to visit the power regulator or the alarm:
any terminals (and the power regulator, the alarm and your ship's pad when it is known) will do. The solver tries every turn of the
map and keeps the one where the places you stood at land on the map's matching features. It only says yes when one answer is
clearly better than all the others, so a wrong guess is rare. Pure maths, no game access.
"""
import cmath
import math

# metres per map unit: Shi Construction fitted 0.325. The solver tries a few sizes around it.
SCALES = (0.30, 0.325, 0.35)
TURN_STEP = 3                       # degrees
CAP_UNITS = 60.0                    # a spot further than this from every matching feature counts as 60 (a miss)
GOOD_UNITS = 22.0                   # average error (map units, about 7 m) a believable answer must beat
MIN_SPOTS = 4                       # when the layout is already known; 5 when she has to choose between layouts (SPOTS_TO_CHOOSE)
SPOTS_TO_CHOOSE = 5
MIN_APART_METRES = 20.0
SEPARATE_DEGREES = 20.0             # answers closer in turn than this are the same answer


def features(data):
    """kind -> [(x, y)] for one map. Kinds: terminal, entry (doors and airlocks), power, alarm, pad, stop (a terminal, the power regulator or the alarm)."""
    found = {"terminal": [], "entry": [], "power": [], "alarm": [], "pad": [], "stop": []}
    for marker in data.get("markers", []):
        kind = str(marker.get("type") or "")
        point = (float(marker["x"]), float(marker["y"]))
        if kind.startswith("terminal"):
            found["terminal"].append(point)
        elif kind in ("door", "airlock"):
            found["entry"].append(point)
        elif kind in ("power", "alarm"):
            found[kind].append(point)
    found["stop"] = found["terminal"] + found["power"] + found["alarm"]      # somewhere you stand still to use something
    centres = {(round(float(c["x"])), round(float(c["y"]))) for c in data.get("circles", [])}
    pads = data.get("pads")
    if len(centres) == 1 and pads and sum(int(v or 0) for v in pads.values()) == 1:
        found["pad"].append((float(data["circles"][0]["x"]), float(data["circles"][0]["y"])))
    return found


def _to_map(a, t, east, north):
    z = (complex(east, north) - t) / a
    return z.real, -z.imag                  # the map's y points down


def _cost(a, t, spots, feats):
    """Average miss in map units. Each feature can explain only ONE spot (two spots 20 m apart cannot both be the same terminal)."""
    options = []
    for index, (kind, east, north) in enumerate(spots):
        x, y = _to_map(a, t, east, north)
        for number, (u, v) in enumerate(feats.get(kind) or ()):
            miss = math.hypot(x - u, y - v)
            if miss < CAP_UNITS:
                options.append((miss, index, kind, number))
    options.sort()
    taken, used, total = set(), set(), 0.0
    for miss, index, kind, number in options:
        if index in used or (kind, number) in taken:
            continue
        used.add(index)
        taken.add((kind, number))
        total += miss
        # a feature of the combined 'stop' kind is also a feature of its own kind: block both names
        if kind == "stop":
            taken.add(("alias", number))
    return (total + CAP_UNITS * (len(spots) - len(used))) / len(spots)


def _spread(spots):
    far = 0.0
    for i, one in enumerate(spots):
        for two in spots[i + 1:]:
            far = max(far, math.hypot(one[1] - two[1], one[2] - two[2]))
    return far


def solve(data, spots, minimum=None):
    """spots: [(kind, east_m, north_m)]. Returns {"a", "t", "error", "next", "n"} or None when there is no clear answer.
    error = average miss in map units for the best answer, next = the same for the best answer that turns the map differently."""
    feats = features(data)
    spots = [s for s in spots if s[0] != "pad" and feats.get(s[0])]          # the pad is only roughly where the ship sat on the circle: left out
    if len(spots) < (minimum or MIN_SPOTS) or _spread(spots) < MIN_APART_METRES:
        return None
    anchor = spots[0]
    tries = []
    for scale in SCALES:
        for turn in range(0, 360, TURN_STEP):
            a = scale * cmath.exp(1j * math.radians(turn))
            for fx, fy in feats[anchor[0]]:
                t = complex(anchor[1], anchor[2]) - a * complex(fx, -fy)
                tries.append((_cost(a, t, spots, feats), turn, a, t))
    tries.sort(key=lambda row: row[0])
    kept = []                                               # the best try of each different turn, each tightened with the same fit
    for row in tries:
        if all(_turn_apart(row[1], other[1]) > SEPARATE_DEGREES for other in kept):
            a, t = row[2], row[3]
            for _ in range(2):
                a, t = _refine(a, t, spots, feats)
            kept.append((_cost(a, t, spots, feats), row[1], a, t))
            if len(kept) >= 6:
                break
    kept.sort(key=lambda row: row[0])
    best = kept[0]
    runner = kept[1] if len(kept) > 1 else None
    return {"a": best[2], "t": best[3], "error": best[0], "next": runner[0] if runner else CAP_UNITS, "n": len(spots)}


def _turn_apart(one, two):
    return abs((one - two + 180) % 360 - 180)


def _refine(a, t, spots, feats):
    """Tighten the fit: match every spot to its nearest feature and fit a clean turn, size and shift to those pairs."""
    zs, ws = [], []
    for kind, east, north in spots:
        x, y = _to_map(a, t, east, north)
        points = feats[kind]
        u, v = min(points, key=lambda p: math.hypot(x - p[0], y - p[1]))
        if math.hypot(x - u, y - v) > CAP_UNITS:
            continue
        zs.append(complex(u, -v))
        ws.append(complex(east, north))
    if len(zs) < 3:
        return a, t
    zc, wc = sum(zs) / len(zs), sum(ws) / len(ws)
    den = sum(abs(z - zc) ** 2 for z in zs)
    if den <= 0:
        return a, t
    na = sum((z - zc).conjugate() * (w - wc) for z, w in zip(zs, ws)) / den
    if not 0.27 <= abs(na) <= 0.38:
        return a, t
    return na, wc - na * zc


SCALE_RANGE = (0.295, 0.355)         # every real settlement measured so far is 0.325 m per unit (Shi); a fit far from that is a coincidence


def clear(result):
    """True when the answer is good enough and clearly better than the best different one."""
    if not result:
        return False
    if not SCALE_RANGE[0] <= abs(result["a"]) <= SCALE_RANGE[1]:
        return False
    return result["error"] <= GOOD_UNITS and result["next"] >= result["error"] * 1.4 + 5.0
