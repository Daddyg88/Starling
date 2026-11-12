"""NEXT TARGET (0.96.3): after a hack she looks up the nearest settlement that nobody has mapped yet, using Spansh.

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


def request_body(system, size=60):
    return {"filters": {"type": {"value": ["Settlement", "Odyssey Settlement", "Planetary Settlement"]}},
            "sort": [{"distance": {"direction": "asc"}}], "size": size, "page": 0, "reference_system": system}


def parse(raw, skip_markets=(), prefer_groups=(), limit=1):
    """Spansh reply -> [{name, system, distance, group, market}] nearest first. Settlements only, never one in skip_markets. Never raises."""
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
        out.append({"name": str(name), "system": str(system), "market": market, "group": group,
                    "distance": round(distance, 1) if isinstance(distance, (int, float)) else None})
    out.sort(key=lambda r: (r["distance"] is None, r["distance"] or 0))
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
        with self._lock:
            cached = self._cache.get(system.lower())
        if cached and now - cached[0] < CACHE_SECONDS:
            raw = cached[1]
        else:
            try:
                raw = self.post("/stations/search", request_body(system))
            except (urllib.error.URLError, OSError, ValueError, TimeoutError) as error:
                log.warning("Next target search failed (%s)", error)
                return None
            except Exception:
                log.exception("Next target search crashed")
                return None
            with self._lock:
                self._cache[system.lower()] = (now, raw)
        found = parse(raw, skip_markets, prefer_groups)
        return found[0] if found else None
