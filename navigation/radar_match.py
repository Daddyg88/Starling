"""Which layout is this? Compares the terminals the radar found with the terminals on each candidate map.

The map's size is known (0.325 metres per map unit) so only its turn and where it sits are unknown. A few terminals pin both down, and
the layout is the candidate whose terminals fit best. The maps were traced by eye (about 10 m off in places) so the match uses a
generous 10 m, and she only says a layout out loud when it is clearly ahead of the others.

Real numbers (Makubuya Engineering Silo, 21 radar spots): Industrial 2 fitted 10, Industrial 1 fitted 8, Industrial 3 fitted 7. So the
radar alone does not settle it: the economy and the pad counts (settlement_track.candidates) must narrow the list first.
"""
import cmath
import itertools

FRAME_SCALE = 0.325
TOLERANCE = 10.0
MIN_POINTS = 3            # fewer terminals than this cannot tell layouts apart
MARGIN = 3                # the best layout must fit at least this many more than the next one
MAX_POINTS = 24           # more than this is slow and adds nothing: the best-seen ones are used


def map_terminals(data):
    """The terminals of a map as complex numbers in metres (x east, y up on the map, before turning)."""
    return [complex(m["x"], -m["y"]) * FRAME_SCALE for m in data.get("markers", []) if str(m.get("type", "")).startswith("terminal")]


def fit(points, terminals, tolerance=TOLERANCE):
    """Best fit of the radar's terminal points (complex metres, east + north*1j) to a map's terminals, turned and moved freely.
    Returns (how many of the points land within `tolerance` of a map terminal, their mean error in metres)."""
    points = list(points)[:MAX_POINTS]
    if len(points) < 2 or len(terminals) < 2:
        return 0, 0.0
    best = (0, 0.0)
    for a, b in itertools.permutations(range(len(points)), 2):
        d = points[a] - points[b]
        if abs(d) < 3.0:
            continue
        for c, e in itertools.permutations(range(len(terminals)), 2):
            z = terminals[c] - terminals[e]
            if abs(abs(z) - abs(d)) > tolerance:
                continue
            turn = d / z
            turn /= abs(turn)
            shift = points[a] - turn * terminals[c]
            moved = [turn * t + shift for t in terminals]
            errors = [min(abs(m - p) for m in moved) for p in points]
            near = [x for x in errors if x < tolerance]
            score = (len(near), -sum(near) / len(near))
            if score > (best[0], -best[1]):
                best = (len(near), sum(near) / len(near))
    return best


def rank(points, maps, candidate_ids, tolerance=TOLERANCE):
    """[(map id, fitted points, mean error)] best first. `maps` is a SettlementMaps (or anything with .get(id) -> map data)."""
    rows = []
    for map_id in candidate_ids:
        data = maps.get(map_id)
        if data is None:
            continue
        fitted, error = fit(points, map_terminals(data), tolerance)
        rows.append((map_id, fitted, error))
    rows.sort(key=lambda r: (-r[1], r[2]))
    return rows


def suggest(points, maps, candidate_ids, tolerance=TOLERANCE):
    """(map id, rows) when one candidate is clearly the best, else (None, rows)."""
    rows = rank(points, maps, candidate_ids, tolerance)
    if len(points) < MIN_POINTS or not rows:
        return None, rows
    if len(rows) == 1:
        return (rows[0][0], rows) if rows[0][1] >= MIN_POINTS else (None, rows)
    if rows[0][1] >= MIN_POINTS and rows[0][1] - rows[1][1] >= MARGIN:
        return rows[0][0], rows
    return None, rows
