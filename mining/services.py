"""
"Where is the nearest black market?" Finds the closest station that offers a service, using Spansh (the same community site as the
neutron plotter and merit mining). One search: stations with that service, nearest to your current system first.

Runs on its own thread (never freezes the game or her voice), cached for 15 minutes, and fails politely when offline.
Fleet carriers are skipped: they move, so the answer could be wrong by the time you get there.
"""
import json
import threading
import time
import urllib.error
import urllib.request

from core.logger import get_logger
from core.secure_open import open_url

log = get_logger("services")

BASE_URL = "https://spansh.co.uk/api"
CACHE_SECONDS = 15 * 60
TIMEOUT_SECONDS = 15.0
BLACK_MARKET = "Black Market"

# What she can look for. (Spansh service name, how she says it, the words you might use). Add a line here and in
# config/brain_intents.json to teach her another one.
SERVICES = [
    ("Black Market", "black market", ["black ?markets?"]),
    ("Material Trader", "material trader", ["material (?:trader|traders|trading)", "materials? (?:trader|traders)"]),
    ("Technology Broker", "technology broker", ["tech(?:nology)? brokers?"]),
    ("Interstellar Factors Contact", "interstellar factors", ["interstellar factors?", "factors? contact", "bounty clearing"]),
    ("Universal Cartographics", "Universal Cartographics", ["universal cartographics", "cartographics"]),
    ("Vista Genomics", "Vista Genomics", ["vista genomics", "genomics"]),
    ("Shipyard", "shipyard", ["ship ?yards?", "ship (?:seller|sellers|dealer|dealers)", "place to buy a ship"]),
    ("Outfitting", "outfitting", ["outfitting", "module (?:seller|sellers|shop|shops|store)", "place to buy modules?"]),
    ("Redemption Office", "redemption office", ["redemption offices?"]),
    ("Pioneer Supplies", "Pioneer Supplies", ["pioneer supplies"]),
    ("Frontline Solutions", "Frontline Solutions", ["frontline solutions"]),
    ("Bartender", "bartender", ["bartenders?", "a bar"]),
]


def request_body(service, reference, size=25):
    return {"filters": {"services": [{"name": service}]}, "sort": [{"distance": {"direction": "asc"}}],
            "size": size, "page": 0, "reference_system": reference}


def parse_stations(raw, service, limit=2):
    """Spansh station search reply -> [{station, system, distance, arrival, type}], nearest first. Never raises."""
    results = raw.get("results") if isinstance(raw, dict) else None
    found = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        name, system = item.get("name"), item.get("system_name")
        kind = str(item.get("type") or "")
        if not name or not system or "carrier" in kind.lower():
            continue
        offered = item.get("services")
        if isinstance(offered, list) and offered:
            names = [str(s.get("name") if isinstance(s, dict) else s).lower() for s in offered]
            if service.lower() not in names:
                continue                       # the service's own filter is not trusted blindly
        distance, arrival = item.get("distance"), item.get("distance_to_arrival")
        found.append({"station": str(name), "system": str(system), "type": kind,
                      "distance": distance if isinstance(distance, (int, float)) else None,
                      "arrival": int(arrival) if isinstance(arrival, (int, float)) else None})
        if len(found) >= limit:
            break
    return found


def post_json(path, body, timeout=TIMEOUT_SECONDS):
    request = urllib.request.Request(BASE_URL + path, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"User-Agent": "Starling/1.0 (Elite Dangerous companion)",
                                              "Content-Type": "application/json", "Accept": "application/json"})
    with open_url(request, timeout=timeout) as reply:
        return json.loads(reply.read().decode("utf-8"))


class ServiceFinder:
    def __init__(self, settings=None, post=post_json, clock=time.monotonic, thread_factory=None):
        self.settings = settings
        self.post = post
        self.clock = clock
        self.thread_factory = thread_factory or (lambda target: threading.Thread(target=target, daemon=True, name="service-finder"))
        self._cache = {}
        self._lock = threading.Lock()

    def enabled(self):
        return self.settings is None or bool(self.settings.get("mining.prices", True))

    def lookup(self, system, service=BLACK_MARKET):
        """(stations, ok). ok is False when Spansh could not be reached. Blocking: call from a thread."""
        key = (str(system).lower(), service.lower())
        now = self.clock()
        with self._lock:
            cached = self._cache.get(key)
            if cached and now - cached[0] < CACHE_SECONDS:
                return cached[1], True
        try:
            stations = parse_stations(self.post("/stations/search", request_body(service, system)), service)
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as error:
            log.warning("Service search failed (%s)", error)
            return [], False
        except Exception:
            log.exception("Service search crashed")
            return [], False
        with self._lock:
            self._cache[key] = (now, stations)
        return stations, True

    def lookup_async(self, system, done, service=BLACK_MARKET):
        def work():
            try:
                stations, ok = self.lookup(system, service)
            except Exception:
                log.exception("Service search crashed")
                stations, ok = [], False
            try:
                done(stations, ok)
            except Exception:
                log.exception("Service answer crashed")
        self.thread_factory(work).start()
