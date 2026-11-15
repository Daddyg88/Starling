"""Adds the terminals you MARKED to the settlement maps, and measures each map's size, from diagnostics ZIPs.

    python3 tools/add_marked_terminals.py starling-diagnostics-*.zip            (shows what it would do)
    python3 tools/add_marked_terminals.py starling-diagnostics-*.zip --write    (does it)

What it trusts: terminals you marked by voice ("mark spot terminal") in a visit where the map shown was known (the ZIP records it). For each
layout it puts all those marks (from every ZIP and visit, the same place counted once) on the map in the one way that lines at least two of them
up with terminals the map already has (within about 8 m, at least 60 m apart) and that is clearly better than every other way. Then
  * a mark with no map terminal near it is a terminal the map does not have: it is added (only when it was marked at least twice, or with --once);
  * the size of the map (metres per map unit) is written to the map file when it has none and the answer is clear.
Nothing is changed when the answer is not clear; the reason is printed. Maps are changed in place, so look at 'git diff' before you commit."""
import argparse
import json
import math
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from navigation import settlement_track                      # noqa: E402
from navigation.settlement_maps import SettlementMaps         # noqa: E402

SAME_PLACE_METRES = 6.0
CAP_UNITS = 350.0                                              # how far past the picture a new terminal may be placed


def load_visits(paths):
    visits, seen = [], set()
    for path in paths:
        path = Path(path)
        try:
            if path.suffix == ".zip":
                with zipfile.ZipFile(path) as z:
                    data = json.loads(z.read("settlement_samples.json").decode("utf-8"))
            else:
                data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, KeyError, ValueError, zipfile.BadZipFile) as error:
            print("Could not read %s: %s" % (path, error))
            continue
        for visit in data if isinstance(data, list) else []:
            key = (visit.get("started"), (visit.get("settlement") or {}).get("MarketID"))
            if key not in seen:
                seen.add(key)
                visits.append(visit)
    return visits


def world(lat, lon, ref_lat, ref_lon, radius):
    return settlement_track.world_xy(lat, lon, ref_lat, ref_lon, radius)


def gather(visits):
    """{(map id, market id): {"ref": (lat, lon, radius), "marks": [(east, north, visit index)]}} for visits whose map is known."""
    found = {}
    for index, visit in enumerate(visits):
        s = visit.get("settlement") or {}
        for mark in visit.get("marks") or []:
            map_id = mark.get("map") or s.get("map_shown")
            if not map_id or "terminal" not in str(mark.get("label", "")).lower() or not mark.get("on_foot", True):
                continue
            if s.get("Latitude") is None or not mark.get("radius"):
                continue
            entry = found.setdefault((map_id, s.get("MarketID")), {"ref": (s["Latitude"], s["Longitude"], mark["radius"]), "marks": [], "ships": [], "name": s.get("Name")})
            east, north = world(mark["lat"], mark["lon"], *entry["ref"])
            entry["marks"].append((east, north, mark.get("time") or ("v%d" % index)))
    for (map_id, market), entry in found.items():
        for visit in visits:
            s = visit.get("settlement") or {}
            if s.get("MarketID") != market or not (visit.get("trail") or []):
                continue
            first = visit["trail"][0]
            entry["ships"].append(world(first[0], first[1], *entry["ref"]))          # the first place on foot: where the ship let you out
            for mark in visit.get("marks") or []:
                if "ship" in str(mark.get("label", "")).lower():
                    entry["ships"].append(world(mark["lat"], mark["lon"], *entry["ref"]))
    return found


def distinct(marks):
    """Marks closer than SAME_PLACE_METRES are one place: [(east, north, number of separate marks there)]."""
    places = []
    for east, north, when in marks:
        for place in places:
            if math.hypot(place["e"] - east, place["n"] - north) < SAME_PLACE_METRES:
                place["visits"].add(when)
                break
        else:
            places.append({"e": east, "n": north, "visits": {when}})
    return [(p["e"], p["n"], len(p["visits"])) for p in places]


def pad_check(data, ships):
    """accept(a, t) for the solver: the ship must stand on (or within 25 m of) one of the map's Medium or Large pads. That is what tells a map
    from the same map turned half way round, which two matching terminals alone cannot."""
    frames = settlement_track.known_pad_frames().get(data["id"], {}).get("pads", [])
    pads = [p for p in frames if p.get("size") in ("Medium", "Large")]
    if not pads or not ships:
        return None

    def accept(a, t):
        scale = abs(a)
        for ship in ships:
            z = (complex(*ship) - t) / a
            x, y = z.real, -z.imag
            if not any(on_pad(pad, x, y, scale) for pad in pads):
                return False
        return True
    return accept


def on_pad(pad, x, y, scale, margin_metres=25.0):
    from navigation.settlement_maps import PAD_METRES
    length, width = PAD_METRES[pad["size"]]
    turn = math.radians(float(pad["facing"]))
    dx, dy = x - float(pad["x"]), y - float(pad["y"])
    along = dx * math.sin(turn) - dy * math.cos(turn)
    across = dx * math.cos(turn) + dy * math.sin(turn)
    return abs(along) <= (length / 2.0 + margin_metres) / scale and abs(across) <= (width / 2.0 + margin_metres) / scale


def solve(data, places, ships=None, rescale=False):
    spots = [("terminal", e, n) for e, n, _ in places]
    own = data.get("scale")
    scales = (float(own) * 0.95, float(own), float(own) * 1.05) if own and not rescale else tuple(round(0.28 + 0.005 * i, 3) for i in range(0, 49))
    seed = settlement_track.Calibration(data["id"], 1.0, 0.0, 0.0, 0.0, 1.0, {})
    return settlement_track.refine_calibration(seed, data, spots, None, turns=range(0, 360), scales=scales, shift=None, accept=pad_check(data, ships))


def add_markers(path, new_markers, bounds):
    """Adds markers to the end of the 'markers' list in the map's own text (keeps the file's layout)."""
    text = path.read_text(encoding="utf-8")
    start = text.index('"markers": [')
    end = text.index("\n ],", start)
    block = "".join(',\n  {\n   "type": "terminal_l0",\n   "x": %d,\n   "y": %d,\n   "marked": true\n  }' % m for m in new_markers)
    text = text[:end] + block + text[end:]
    if bounds is not None:
        if '"bounds"' in text:
            text = re.sub(r'"bounds": \[[^\]]*\]', '"bounds": %s' % json.dumps(bounds), text, count=1)
        else:
            text = text.replace('"credit"', '"bounds": %s,\n "credit"' % json.dumps(bounds), 1)
    json.loads(text)
    path.write_text(text, encoding="utf-8")


def set_scale(path, scale, replace=False):
    text = path.read_text(encoding="utf-8")
    if re.search(r'^ "scale": [0-9.]+,$', text, re.M):
        if not replace:
            return False
        text = re.sub(r'^ "scale": [0-9.]+,$', ' "scale": %s,' % scale, text, count=1, flags=re.M)
    else:
        text = text.replace('"credit"', '"scale": %s,\n "credit"' % scale, 1)
    json.loads(text)
    path.write_text(text, encoding="utf-8")
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("files", nargs="+", help="diagnostics ZIPs (or settlement_samples.json files)")
    parser.add_argument("--write", action="store_true", help="change the map files (default: only show)")
    parser.add_argument("--rescale", action="store_true", help="measure the map's size again even when the map already has one (and replace it)")
    parser.add_argument("--once", action="store_true", help="add a terminal marked in one visit only")
    args = parser.parse_args(argv)
    maps = SettlementMaps()
    groups = gather(load_visits(args.files))
    if not groups:
        print("No marked terminals on a known map in those files.")
        return 0
    by_map, ship_of = {}, {}
    for (map_id, market), entry in groups.items():
        by_map.setdefault(map_id, []).extend(entry["marks"])
        ship_of.setdefault(map_id, []).extend(entry["ships"])
    for map_id, marks in sorted(by_map.items()):
        data = maps.get(map_id)
        if data is None:
            print("%s: no such map" % map_id)
            continue
        places = distinct(marks)
        print("\n%s: %d marked places (%s)" % (map_id, len(places), ", ".join("marked %dx" % n for _, _, n in places)))
        found = solve(data, places, ship_of.get(map_id), args.rescale)
        if found is None:
            print("  no clear answer (fewer than two marks match map terminals 60 m or more apart, or two answers fit about as well). Nothing changed.")
            continue
        cal, matched, missing = found
        print("  %d match map terminals, %d do not; %.3f m per map unit, turned %.0f degrees" % (matched, missing, abs(cal.a), cal.turn_degrees()))
        feats = settlement_track.outside_features(data)["terminal"]
        new = []
        for east, north, visits in places:
            x, y = cal.from_world(east, north)
            if min(math.hypot(x - u, y - v) for u, v in feats) <= settlement_track.REFINE_MATCH_UNITS:
                continue
            W, H = float(data["size"][0]), float(data["size"][1])
            bx0, by0, bx1, by1 = settlement_track_bounds(data)
            ok = -CAP_UNITS <= x <= W + CAP_UNITS and -CAP_UNITS <= y <= H + CAP_UNITS
            sure = visits >= 2 or args.once
            print("  not on the map: (%.0f, %.0f) marked %dx -> %s" % (x, y, visits,
                  "will add" if (sure and ok) else ("too far from the picture" if not ok else "marked only once, not added (use --once)")))
            if sure and ok:
                new.append((round(x), round(y)))
        scale = round(abs(cal.a), 3)
        needs_scale = ("scale" not in data or args.rescale) and abs(scale - float(data.get("scale") or 0.325)) > 0.01 and (matched >= 3 or max(
            math.hypot(a[0] - b[0], a[1] - b[1]) for a in places for b in places) >= 100)
        if needs_scale:
            print("  this map's size looks like %s (the shared one is 0.325)" % scale)
        if args.write:
            path = ROOT / "maps" / "settlements" / ("%s.json" % map_id)
            if new:
                bx0, by0, bx1, by1 = settlement_track_bounds(data)
                W, H = float(data["size"][0]), float(data["size"][1])
                nb = [min(bx0, min(m[0] for m in new) - 30, 0), min(by0, min(m[1] for m in new) - 30, 0),
                      max(bx1, max(m[0] for m in new) + 30, W), max(by1, max(m[1] for m in new) + 30, H)]
                nb = [int(math.floor(v)) if i < 2 else int(math.ceil(v)) for i, v in enumerate(nb)]
                add_markers(path, new, nb if nb != [int(bx0), int(by0), int(bx1), int(by1)] else None)
                print("  added %d terminal(s) to %s" % (len(new), path.name))
            if needs_scale and set_scale(path, scale, args.rescale):
                print("  wrote scale %s to %s" % (scale, path.name))
    return 0


def settlement_track_bounds(data):
    from navigation import settlement_maps
    return settlement_maps.bounds(data)


if __name__ == "__main__":
    sys.exit(main())
