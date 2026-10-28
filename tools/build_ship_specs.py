"""
Turns the plain-text list of Elite ships and their stats into config/ships_specs.json (what Starling reads).

How to use (only needed when you have a newer text list):
    python tools/build_ship_specs.py  path\\to\\all_ships_and_specs.TXT

The text list is copied from the Elite Dangerous wiki (https://elite-dangerous.fandom.com, CC BY-SA). Each ship starts with its
name followed by the word "Overview"; after that come pairs of lines (a label, then its value).
"""
import json
import re
import sys
from pathlib import Path

SINGLE = {"Manufacturer": "manufacturer", "Years Produced": "years", "Type": "role", "Cost": "cost", "ARX": "arx", "Insurance": "insurance",
          "Faction": "faction", "Faction Rank": "rank", "Expansion": "expansion", "Landing Pad Size": "pad", "Dimensions": "dimensions",
          "Pilot Seats": "seats", "Multicrew": "multicrew", "Fighter Bay": "fighter_bay", "Hull Mass": "mass", "Mass Lock Factor": "mass_lock",
          "Armour": "armour", "Armour Hardness": "hardness", "Shields": "shields", "Heat Capacity": "heat", "Fuel Capacity": "fuel",
          "SCO Optimised": "sco", "Manoeuvr-": "manoeuvrability", "Top Speed": "speed", "Boost Speed": "boost",
          "Unladen Jump Range": "jump", "Cargo Capacity": "cargo"}
LISTS = {"Hardpoints": "hardpoints", "Internal Compartments": "internal", "Reserved Compartments": "reserved", "Reserved Hardpoints": "reserved_hardpoints"}
SKIP = {"Overview", "Specifications", "Outfitting", "ability"}


def parse(text):
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    ships, current, label = [], None, None
    for index, line in enumerate(lines):
        if index + 1 < len(lines) and lines[index + 1] == "Overview":
            current = {"name": line}
            ships.append(current)
            label = None
            continue
        if current is None or line in SKIP:
            continue
        if line in SINGLE or line in LISTS:
            label = line
            key = SINGLE.get(line) or LISTS[line]
            current.setdefault(key, [])
            continue
        if label is not None:
            current[SINGLE.get(label) or LISTS[label]].append(line)
    for ship in ships:
        for key, value in list(ship.items()):
            if key == "name":
                continue
            if key in LISTS.values() or key in ("speed", "boost", "jump", "cargo"):
                ship[key] = value
            else:
                ship[key] = " ".join(value)
    return ships


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    ships = parse(Path(argv[1]).read_text(encoding="utf-8", errors="replace"))
    out = Path(__file__).resolve().parent.parent / "config" / "ships_specs.json"
    out.write_text(json.dumps({"_help": "Ship stats for Starling, from the Elite Dangerous wiki (CC BY-SA). Rebuilt by tools/build_ship_specs.py.",
                               "ships": ships}, indent=1, ensure_ascii=False), encoding="utf-8")
    print("Wrote %d ships to %s" % (len(ships), out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
