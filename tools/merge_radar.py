"""Merges the radar points from testers' diagnostics zips into one survey, and shows what the maps could learn from it.

Run it on your PC (or here) like this:
    python tools/merge_radar.py  zip1.zip  zip2.zip  folder_of_zips   [--apply]

What it does:
  1. reads radar_points.json from every zip (or every radar_points.json file you name)
  2. merges the settlements by MarketID (two testers' sightings of the same terminal become one point)
  3. writes maps/radar_survey.json: which settlements have been surveyed (this is what she reads to say 'already mapped')
  4. for each settlement whose layout is known (maps/known_settlements.json) it fits the traced map to the measured terminals and
     prints how far each map terminal is from what was measured
  5. with --apply, a map terminal is moved to the measured spot ONLY when at least 2 sightings agree and the fit is good (at least 4
     terminals fit within 8 m). Everything else is left exactly as it was. The old maps are copied to maps/settlements/_backup first.
Nothing is changed without --apply.
"""
import cmath
import io
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from navigation import radar_match                      # noqa: E402
from navigation.radar_points import MERGE_METRES, PointStore   # noqa: E402

FIT_TOLERANCE = 8.0
MIN_FITTED = 4
MIN_SIGHTINGS = 2


def read_sources(args):
    blobs = []
    for arg in args:
        path = Path(arg)
        files = sorted(path.glob("*.zip")) if path.is_dir() else [path]
        for f in files:
            if f.suffix.lower() == ".zip":
                try:
                    with zipfile.ZipFile(f) as z:
                        if "radar_points.json" in z.namelist():
                            blobs.append((f.name, json.loads(z.read("radar_points.json").decode("utf-8"))))
                except (OSError, zipfile.BadZipFile, ValueError):
                    print("Could not read", f)
            elif f.name.endswith(".json"):
                try:
                    blobs.append((f.name, json.loads(f.read_text(encoding="utf-8"))))
                except (OSError, ValueError):
                    print("Could not read", f)
    return blobs


def merge(blobs):
    """-> {market: {"name", "layout", "group", "pads", "pictures", "radius", "origin", "points", "sources"}} (points merged)."""
    out = {}
    for source, blob in blobs:
        for key, e in (blob.get("settlements") or {}).items():
            if not isinstance(e, dict) or not e.get("origin") or not e.get("radius"):
                continue
            mine = out.setdefault(key, {"name": e.get("name"), "layout": e.get("layout"), "group": e.get("group"), "pads": e.get("pads"),
                                        "pictures": 0, "radius": e["radius"], "origin": e["origin"], "points": [], "sources": []})
            mine["pictures"] += int(e.get("pictures", 0))
            mine["layout"] = mine["layout"] or e.get("layout")
            mine["sources"].append(source)
            store = PointStore(path=Path("/nonexistent/radar.json"))
            store.data = {"x": {"points": mine["points"], "pictures": 0, "cells": [], "origin": mine["origin"], "radius": mine["radius"]}}
            for p in e.get("points", []):
                for _ in range(max(1, int(p.get("n", 1)))):
                    store.add_picture("x", [(p["kind"], p["lat"], p["lon"])], tuple(mine["origin"]), mine["radius"])
            mine["points"] = store.data["x"]["points"]
    return out


def survey(merged):
    return {key: {"name": e["name"], "layout": e["layout"], "pictures": e["pictures"],
                  "terminals": sum(1 for p in e["points"] if p["kind"] == "terminal"),
                  "points": len(e["points"]), "testers": len(set(e["sources"]))} for key, e in merged.items()}


def metres(e, p):
    import math
    per = math.pi / 180.0 * e["radius"]
    o = e["origin"]
    return complex((p["lon"] - o[1]) * per * math.cos(math.radians(o[0])), (p["lat"] - o[0]) * per)


def fit_map(e, data):
    """Best turn and shift of the map onto the measured terminals: (turn, shift, fitted) or None."""
    points = [metres(e, p) for p in e["points"] if p["kind"] == "terminal"]
    terminals = radar_match.map_terminals(data)
    best = None
    for a in range(len(points)):
        for b in range(len(points)):
            if a == b or abs(points[a] - points[b]) < 3:
                continue
            for c in range(len(terminals)):
                for d in range(len(terminals)):
                    if c == d:
                        continue
                    z = terminals[c] - terminals[d]
                    if abs(abs(z) - abs(points[a] - points[b])) > FIT_TOLERANCE:
                        continue
                    turn = (points[a] - points[b]) / z
                    turn /= abs(turn)
                    shift = points[a] - turn * terminals[c]
                    fitted = sum(1 for t in terminals if min(abs(turn * t + shift - p) for p in points) < FIT_TOLERANCE)
                    if best is None or fitted > best[2]:
                        best = (turn, shift, fitted)
    return best


def corrections(e, data):
    """[(marker index, old (x, y), new (x, y), sightings)] for the terminals that can safely be moved."""
    fit = fit_map(e, data)
    if fit is None or fit[2] < MIN_FITTED:
        return fit, []
    turn, shift, _fitted = fit
    points = [(metres(e, p), p["n"]) for p in e["points"] if p["kind"] == "terminal"]
    out = []
    for index, m in enumerate(data.get("markers", [])):
        if not str(m.get("type", "")).startswith("terminal"):
            continue
        where = turn * (complex(m["x"], -m["y"]) * radar_match.FRAME_SCALE) + shift
        spot, n = min(points, key=lambda pn: abs(pn[0] - where))
        if abs(spot - where) < FIT_TOLERANCE and n >= MIN_SIGHTINGS:
            back = (spot - shift) / turn / radar_match.FRAME_SCALE           # the measured spot in map units
            out.append((index, (m["x"], m["y"]), (round(back.real), round(-back.imag)), n))
    return fit, out


def main(argv):
    apply = "--apply" in argv
    blobs = read_sources([a for a in argv if not a.startswith("--")])
    if not blobs:
        print("No radar_points.json found. Give me the zips (or the folder they are in).")
        return 1
    merged = merge(blobs)
    (ROOT / "maps" / "radar_survey.json").write_text(json.dumps(survey(merged), indent=1), encoding="utf-8")
    print("Settlements surveyed: %d (written to maps/radar_survey.json)" % len(merged))
    known = {}
    try:
        known = json.loads((ROOT / "maps" / "known_settlements.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    folder = ROOT / "maps" / "settlements"
    for key, e in merged.items():
        layout = known.get(key) or e.get("layout")
        terminals = sum(1 for p in e["points"] if p["kind"] == "terminal")
        print("\n%s (%s): %d pictures, %d terminals, layout %s" % (e["name"], key, e["pictures"], terminals, layout or "unknown"))
        path = folder / ("%s.json" % layout) if layout else None
        if path is None or not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        fit, changes = corrections(e, data)
        if fit is None or fit[2] < MIN_FITTED:
            print("  the map does not fit well enough yet (%s terminals fit): nothing to change" % (fit[2] if fit else 0))
            continue
        print("  %d map terminals fit within %.0f m; %d can be moved" % (fit[2], FIT_TOLERANCE, len(changes)))
        for index, old, new, n in changes:
            print("   terminal %d: %s -> %s  (%d sightings)" % (index, old, new, n))
        if apply and changes:
            backup = folder / "_backup"
            backup.mkdir(exist_ok=True)
            shutil.copy(path, backup / path.name)
            for index, _old, new, _n in changes:
                data["markers"][index]["x"], data["markers"][index]["y"] = new
            path.write_text(json.dumps(data, indent=1), encoding="utf-8")
            print("  APPLIED to", path.name, "(old copy in _backup)")
    if not apply:
        print("\nNothing was changed. Add --apply to move the terminals listed above.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
