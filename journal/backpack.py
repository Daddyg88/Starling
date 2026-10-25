"""
Reads Backpack.json (the game writes it into the journal folder whenever your backpack changes).

It lists what you carry:  {"Consumables": [{"Name": "healthpack", "Count": 3}, {"Name": "amm_grenade_frag", "Count": 1}], "Items": [...], ...}
Names are the game's internal names, so she matches by the wording inside them ("grenade", "healthpack", "energycell").
Honest limit: the exact names were written from the journal manual and memory, not from your game. The log shows what she reads.
"""

import json
from pathlib import Path


def read_counts(folder):
    """{lowercase name: count} for everything in the backpack, or None when the file is missing or unreadable."""
    if not folder:
        return None
    try:
        data = json.loads((Path(folder) / "Backpack.json").read_text(encoding="utf-8", errors="ignore"))
    except (OSError, ValueError):
        return None
    counts = {}
    for group in ("Items", "Components", "Consumables", "Data"):
        for entry in data.get(group) or []:
            try:
                name = str(entry.get("Name", "")).lower()
                counts[name] = counts.get(name, 0) + int(entry.get("Count", 0))
            except (AttributeError, TypeError, ValueError):
                continue
    return counts


def count_matching(counts, *words):
    """Total of every item whose name contains any of the words."""
    return sum(n for name, n in (counts or {}).items() if any(w in name for w in words))


GRENADE_NAMES = {"frag": "frag", "emp": "EMP", "shield": "shield"}


def grenade_label(name):
    """amm_grenade_frag -> 'frag'. Unknown kinds just say 'grenade'."""
    low = str(name).lower()
    for word, label in GRENADE_NAMES.items():
        if word in low:
            return label
    return "grenade"
