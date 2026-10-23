"""The destination you picked in Elite's galaxy map. The game writes your plotted route to NavRoute.json (next to the
journal files); the LAST system in it is where you want to go."""

import json
from pathlib import Path


def read_route(folder):
    """All the systems of the route plotted in the game, in order ([] if none)."""
    if not folder:
        return []
    try:
        with open(Path(folder) / "NavRoute.json", "r", encoding="utf-8") as handle:
            route = json.load(handle).get("Route") or []
    except (OSError, ValueError, AttributeError):
        return []
    return [h["StarSystem"].strip() for h in route if isinstance(h, dict) and isinstance(h.get("StarSystem"), str) and h["StarSystem"].strip()]


def choose_target(folder, state):
    """Where the commander wants to go. "Plot course" writes NavRoute.json (its last system is the goal). "Set Target" only
    selects a system (the journal's FSDTarget). If the selected system is not part of the plotted route it is the newer wish."""
    route = read_route(folder)
    picked = str(getattr(state, "fsd_target", "") or "").strip()
    here = str(getattr(state, "system", "") or "").casefold()
    if picked and picked.casefold() != here and picked.casefold() not in [r.casefold() for r in route]:
        return picked
    return route[-1] if route else ""


def read_target(folder):
    """The system name at the end of the route plotted in the game, or "" if there is none."""
    if not folder:
        return ""
    try:
        with open(Path(folder) / "NavRoute.json", "r", encoding="utf-8") as handle:
            route = json.load(handle).get("Route") or []
    except (OSError, ValueError, AttributeError):
        return ""
    for hop in reversed(route):
        name = hop.get("StarSystem") if isinstance(hop, dict) else None
        if isinstance(name, str) and name.strip():
            return name.strip()
    return ""
