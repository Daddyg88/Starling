"""
Finds where to sell what you mined, using Ardent (a free, community price service built from the game's own market data).

Inara has no public price lookup, so it cannot be used for this. Ardent needs no sign-up or key.
Every lookup runs in a background thread (so the game and her voice never freeze), is cached for 15 minutes,
and fails politely when you are offline.

The answer comes back as a list of {"station","system","price","demand","distance","pad"}, best price first.
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from core.logger import get_logger

log = get_logger("prices")

BASE_URL = "https://api.ardent-insight.com/v2"
CACHE_SECONDS = 15 * 60
TIMEOUT_SECONDS = 8.0
PAD_NAMES = {1: "small", 2: "medium", 3: "large"}


def build_url(system, commodity, max_distance=100, max_age_days=7, min_demand=50):
    return "%s/system/name/%s/commodity/name/%s/nearby/imports?%s" % (
        BASE_URL, urllib.parse.quote(str(system), safe=""), urllib.parse.quote(str(commodity), safe=""),
        urllib.parse.urlencode({"minVolume": int(min_demand), "maxDaysAgo": int(max_age_days),
                                "fleetCarriers": "false", "maxDistance": int(max_distance)}))


def parse(raw, limit=3):
    """Ardent's reply (a list of markets) -> clean results, best price first. Never raises; junk is skipped."""
    if isinstance(raw, dict):
        for key in ("results", "data", "markets"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
    if not isinstance(raw, list):
        return []
    found = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        price = item.get("sellPrice")
        station = item.get("stationName")
        system = item.get("systemName")
        if not isinstance(price, (int, float)) or price <= 0 or not station or not system:
            continue
        if str(item.get("stationType") or "").lower().replace(" ", "") == "fleetcarrier":
            continue
        distance = item.get("distance")
        if not isinstance(distance, (int, float)):
            distance = item.get("distanceFromSystem") if isinstance(item.get("distanceFromSystem"), (int, float)) else None
        pad = item.get("maxLandingPadSize")
        found.append({"station": str(station), "system": str(system), "price": int(price),
                      "demand": item.get("demand") if isinstance(item.get("demand"), (int, float)) else None,
                      "distance": distance, "pad": PAD_NAMES.get(pad, "")})
    found.sort(key=lambda r: -r["price"])
    return found[:limit]


def fetch_json(url, timeout=TIMEOUT_SECONDS):
    request = urllib.request.Request(url, headers={"User-Agent": "Starling/1.0 (Elite Dangerous companion)",
                                                  "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as reply:
        return json.loads(reply.read().decode("utf-8"))


class PriceFinder:
    def __init__(self, settings=None, fetch=fetch_json, clock=time.monotonic, thread_factory=None):
        self.settings = settings
        self.fetch = fetch
        self.clock = clock
        self.thread_factory = thread_factory or (lambda target: threading.Thread(target=target, daemon=True, name="price-finder"))
        self._cache = {}
        self._lock = threading.Lock()

    def enabled(self):
        return self.settings is None or bool(self.settings.get("mining.prices", True))

    def lookup(self, system, commodity):
        """(results, ok). ok is False when the service could not be reached. Blocking: call from a thread."""
        key = (str(system).lower(), str(commodity).lower())
        now = self.clock()
        with self._lock:
            cached = self._cache.get(key)
            if cached and now - cached[0] < CACHE_SECONDS:
                return cached[1], True
        try:
            raw = self.fetch(build_url(system, commodity))
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as error:
            log.warning("Price lookup failed (%s)", error)
            return [], False
        except Exception:
            log.exception("Price lookup crashed")
            return [], False
        results = parse(raw)
        with self._lock:
            self._cache[key] = (now, results)
        return results, True

    def lookup_async(self, system, commodity, done):
        """Run lookup() in the background and call done(results, ok) when it finishes."""
        def work():
            try:
                results, ok = self.lookup(system, commodity)
            except Exception:
                log.exception("Price lookup crashed")
                results, ok = [], False
            try:
                done(results, ok)
            except Exception:
                log.exception("Price answer crashed")
        self.thread_factory(work).start()
