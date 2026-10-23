"""The destination you picked in Elite's galaxy map. The game writes your plotted route to NavRoute.json (next to the
journal files); the LAST system in it is where you want to go."""

import json
from pathlib import Path


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
