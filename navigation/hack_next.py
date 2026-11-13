"""NEXT TARGET (0.96.3, pirates 0.96.6): after a hack she looks up the nearest settlement that nobody has mapped yet, using Spansh. Bases in systems run by an Anarchy government (pirate bases) come first.

UNTESTED against the real Spansh: the station search is the same one the black-market finder uses (mining/services.py, which works), but
the settlement and economy filter names below are a best guess. So the reply is also checked here, on our side (type contains "settlement",
economy matches), and ANY problem just makes her say there is nothing to suggest. Nothing here can break the hack.
"""
import json
import threading
import time
import urllib.error

from core.logger import get_logger
from mining.services import post_json

log = get_logger("hack_next")

ECONOMY_OF_GROUP = {"Agriculture": "Agriculture", "Industrial": "Industrial", "Extraction": "Extraction", "Military": "Military",
                    "Tourist": "Tourism", "High Tech": "High Tech"}
GROUP_OF_ECONOMY = {v.lower(): k for k, v in ECONOMY_OF_GROUP.items()}
CACHE_SECONDS = 15 * 60


def request_body(system, size=60, anarchy=True):
    """The station search. With anarchy=True it also asks for systems run by an Anarchy government (pirate bases: easy to raid, and where the
    stolen files went). The filter name 'government' is a GUESS: if Spansh refuses it, find() asks again without it and sorts the pirates first itself."""
    filters = {"type": {"value": ["Settlement", "Odyssey Settlement", "Planetary Settlement"]}}
    if anarchy:
        filters["government"] = {"value": ["Anarchy"]}
    return {"filters": filters, "sort": [{"distance": {"direction": "asc"}}], "size": size, "page": 0, "reference_system": system}


def is_anarchy(item):
    """True when the reply says the system's controlling faction is an Anarchy (pirates). The field names are guesses; anything else is False."""
    for key in ("controlling_minor_faction_government", "government", "system_government", "controlling_faction_government"):
        value = item.get(key)
        if isinstance(value, str) and value.strip().lower() == "anarchy":
            return True
    return False


def parse(raw, skip_markets=(), prefer_groups=(), limit=1):
    """Spansh reply -> [{name, system, distance, group, market, pirate}] pirate bases first, then nearest. Settlements only, never one in skip_markets. Never raises."""
    results = raw.get("results") if isinstance(raw, dict) else None
    out = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        name, system = item.get("name"), item.get("system_name")
        kind = str(item.get("type") or "").lower()
        if not name or not system or "settlement" not in kind:
            continue
        market = str(item.get("market_id") or item.get("id") or "")
        if market and market in skip_markets:
            continue
        economy = str(item.get("primary_economy") or "").lower()
        group = GROUP_OF_ECONOMY.get(economy)
        if group is None:
            continue
        if prefer_groups and group not in prefer_groups:
            continue
        distance = item.get("distance")
        out.append({"name": str(name), "system": str(system), "market": market, "group": group, "pirate": is_anarchy(item),
                    "distance": round(distance, 1) if isinstance(distance, (int, float)) else None})
    out.sort(key=lambda r: (not r["pirate"], r["distance"] is None, r["distance"] or 0))             # pirate bases first, then the nearest
    return out[:limit]


class NextTarget:
    def __init__(self, post=post_json, clock=time.monotonic):
        self.post = post
        self.clock = clock
        self._cache = {}
        self._lock = threading.Lock()

    def find(self, system, skip_markets=(), prefer_groups=()):
        """The nearest suggestion or None. Blocking (a web call): run it in a thread."""
        if not system:
            return None
        now = self.clock()
        raw = None
        for anarchy in (True, False):
            cache_key = (system.lower(), anarchy)
            with self._lock:
                cached = self._cache.get(cache_key)
            if cached and now - cached[0] < CACHE_SECONDS:
                raw = cached[1]
            else:
                try:
                    raw = self.post("/stations/search", request_body(system, anarchy=anarchy))
                except (urllib.error.URLError, OSError, ValueError, TimeoutError) as error:
                    log.warning("Next target search failed (anarchy filter %s): %s", anarchy, error)
                    continue                       # Spansh may not know the anarchy filter: try the plain search
                except Exception:
                    log.exception("Next target search crashed")
                    return None
                with self._lock:
                    self._cache[cache_key] = (now, raw)
            if parse(raw, skip_markets, prefer_groups):
                break
        if raw is None:
            return None
        found = parse(raw, skip_markets, prefer_groups)
        return found[0] if found else None
