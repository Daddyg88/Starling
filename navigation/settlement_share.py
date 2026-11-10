"""SHARED SETTLEMENT LINE-UPS: checking and merging the line-ups (which layout, which way turned) that players have worked out.

Every settlement is turned its own way, and nobody can walk 100,000 of them. But a settlement only has to be solved ONCE, by anyone: its
line-up never changes. Starling saves each one she works out in data/settlement_calibration.json (it goes into the diagnostics zip), and
the maintainer merges the good ones into maps/known_calibrations.json, which ships with the app. This file holds the checks used when
loading that shipped file and by tools/merge_calibrations.py.
"""
import cmath
import math

SCALE_RANGE = (0.27, 0.38)          # metres per map unit (Shi Construction measured 0.325)
TURN_TOLERANCE_DEGREES = 12.0       # two line-ups of one settlement that differ by more than this disagree
KEYS = ("v", "map", "a", "t", "ref", "radius")


def _pair(value):
    return isinstance(value, (list, tuple)) and len(value) == 2 and all(isinstance(x, (int, float)) and math.isfinite(x) for x in value)


def problem(entry, map_ids=None):
    """None if the line-up looks sane, otherwise a short reason it is not trusted."""
    if not isinstance(entry, dict):
        return "not an object"
    if entry.get("disabled"):
        return "switched off by the player"
    if entry.get("v") != 2:
        return "saved by an older version"
    for key in KEYS:
        if key not in entry:
            return "missing %s" % key
    if not (_pair(entry["a"]) and _pair(entry["t"]) and _pair(entry["ref"])):
        return "numbers are not numbers"
    if not isinstance(entry["radius"], (int, float)) or entry["radius"] < 1000:
        return "planet radius looks wrong"
    if map_ids is not None and entry["map"] not in map_ids:
        return "unknown map %s" % entry["map"]
    scale = abs(complex(*entry["a"]))
    if not SCALE_RANGE[0] <= scale <= SCALE_RANGE[1]:
        return "map size %.3f m per unit is not believable" % scale
    if not (-90 <= entry["ref"][0] <= 90 and -180 <= entry["ref"][1] <= 180):
        return "position is not on a planet"
    return None


def turn(entry):
    return math.degrees(cmath.phase(complex(*entry["a"])))


def evidence(entry):
    """How well proved a line-up is: more places stood at wins, then the smaller miss."""
    return (int(entry.get("n") or 0), -float(entry.get("err") if entry.get("err") is not None else 99.0))


def agree(one, two):
    if one["map"] != two["map"]:
        return False
    gap = abs((turn(one) - turn(two) + 180.0) % 360.0 - 180.0)
    return gap <= TURN_TOLERANCE_DEGREES


def merge(shipped, new, map_ids=None):
    """Adds the good line-ups in `new` (MarketID -> entry) to `shipped`. Returns (merged, report) where report is a list of lines.
    A market already shipped is only replaced by a line-up that AGREES with it and has better evidence; a disagreement is reported
    and the shipped one is kept (somebody has to look at it)."""
    merged = {k: v for k, v in shipped.items() if not str(k).startswith("_")}
    report = []
    for market, entry in sorted(new.items()):
        if str(market).startswith("_"):
            continue
        why = problem(entry, map_ids)
        name = entry.get("name") if isinstance(entry, dict) else None
        label = "%s (%s)" % (market, name) if name else str(market)
        if why:
            report.append("skipped %s: %s" % (label, why))
            continue
        have = merged.get(market)
        if have is None:
            merged[market] = entry
            report.append("added %s: %s, turned %.0f degrees" % (label, entry["map"], turn(entry)))
        elif not agree(have, entry):
            report.append("CONFLICT %s: shipped says %s turned %.0f, new says %s turned %.0f. Kept the shipped one; check it by hand."
                          % (label, have["map"], turn(have), entry["map"], turn(entry)))
        elif evidence(entry) > evidence(have):
            merged[market] = entry
            report.append("improved %s: more evidence" % label)
        else:
            report.append("already have %s" % label)
    return merged, report
