"""
Your engineering materials: how many you hold and how full each store is.

Storage limits per grade: grade 1 = 300, grade 2 = 250, grade 3 = 200, grade 4 = 150, grade 5 = 100 (raw materials stop at grade 4).
config/materials.json gives every material's grade (from the EDCD FDevIDs list).
The game's "Materials" line at the start gives the counts; collecting, discarding, synthesising, crafting, trading and research change them.
If she starts in the middle of a session the counts catch up at the next "Materials" line, and until then percentages can be a little off.
"""

import json

from core import paths
from core.logger import get_logger

log = get_logger("materials")

LIMITS = {1: 300, 2: 250, 3: 200, 4: 150, 5: 100}
_table = None


def table():
    global _table
    if _table is None:
        try:
            with open(paths.CONFIG_DIR / "materials.json", "r", encoding="utf-8") as handle:
                _table = json.load(handle).get("materials", {})
        except (OSError, ValueError):
            log.exception("Could not read config/materials.json")
            _table = {}
    return _table


def key(name):
    return str(name or "").strip().lower()


def info(name):
    return table().get(key(name))


def limit(name):
    found = info(name)
    return LIMITS.get(found["g"]) if found else None


def display_name(name):
    found = info(name)
    return found["n"] if found else str(name or "").replace("_", " ")


def percent(state, name):
    """Whole percent full for one material, or None when its grade is unknown."""
    cap = limit(name)
    if not cap:
        return None
    held = (getattr(state, "materials", None) or {}).get(key(name), 0)
    return min(100, int(round(100.0 * held / cap)))


def add(state, name, count):
    store = state.materials
    k = key(name)
    store[k] = max(0, store.get(k, 0) + int(count or 0))


def load_all(state, entry):
    """The 'Materials' line: replaces everything."""
    store = {}
    for group in ("Raw", "Manufactured", "Encoded"):
        for item in entry.get(group) or []:
            if isinstance(item, dict) and item.get("Name"):
                store[key(item["Name"])] = int(item.get("Count", 0) or 0)
    state.materials = store


def spend(state, items, name_key="Name", count_key="Count"):
    for item in items or []:
        if isinstance(item, dict) and item.get(name_key):
            add(state, item[name_key], -int(item.get(count_key, 0) or 0))
