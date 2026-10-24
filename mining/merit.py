"""
MERIT MINING: "I want to go merit mining". Finds systems that

  * are CONTROLLED by the Power you are pledged to (Powerplay: Fortified, Stronghold or Exploited),
  * have a planet with a PRISTINE METALLIC RING, and
  * have a station or outpost (never a fleet carrier) where a mined metal is wanted: demand of 2000 tonnes or more.

The data comes from Spansh (https://spansh.co.uk), the same community site as the neutron plotter:
  1. body search   : Metallic ring + Pristine reserves + system controlled by your Power, nearest first
  2. station search: in those systems, a market that wants one of the metals (demand 2000 or more)
The two answers are put together and the nearest matches come back as {system, station, body, material, demand, price, distance}.

Runs on its own thread (never freezes the game or her voice), is cached for 15 minutes and fails politely when offline.
Not "influenced" systems: Spansh only says which Power CONTROLS a system, so a system that is merely influenced is not found.
"""

import json
import threading
import time
import urllib.error
import urllib.request

from core.logger import get_logger

log = get_logger("merit")

BASE_URL = "https://spansh.co.uk/api"
CACHE_SECONDS = 15 * 60
TIMEOUT_SECONDS = 15.0
MIN_DEMAND = 2000                         # tonnes a station must want
MAX_SYSTEMS = 40                          # how many nearby systems with a good ring to check for a market
DEFAULT_COMMODITIES = ("Platinum", "Osmium", "Painite", "Palladium")
POWERS = ("Aisling Duval", "Archon Delaine", "Arissa Lavigny-Duval", "Denton Patreus", "Edmund Mahon", "Felicia Winters",
          "Jerome Archer", "Li Yong-Rui", "Nakato Kaine", "Pranav Antal", "Yuri Grom", "Zemina Torval")


def bodies_request(power, reference):
    return {"filters": {"rings": [{"type": ["Metallic"]}], "reserve_level": {"value": ["Pristine"]},
                        "system_controlling_power": {"value": [power]}},
            "sort": [{"distance": {"direction": "asc"}}], "size": 100, "page": 0, "reference_system": reference}


def stations_request(systems, commodity, reference):
    return {"filters": {"system_name": {"value": list(systems)},
                        "market": [{"name": commodity, "demand": {"comparison": "<=>", "value": [MIN_DEMAND, 1000000000]}}]},
            "sort": [{"distance": {"direction": "asc"}}], "size": 100, "page": 0, "reference_system": reference}


def parse_bodies(raw):
    """Spansh body search reply -> [{"system","body","distance","state"}], nearest first, one per system."""
    results = raw.get("results") if isinstance(raw, dict) else None
    seen, found = set(), []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        system, body = item.get("system_name"), item.get("name")
        if not system or not body or system in seen:
            continue
        if str(item.get("reserve_level") or "Pristine") != "Pristine":
            continue                                       # double-check: the service's own filter is not trusted blindly
        types = [r.get("type") for r in (item.get("rings") or []) if isinstance(r, dict)]
        if types and "Metallic" not in types:
            continue
        seen.add(system)
        distance = item.get("distance")
        found.append({"system": str(system), "body": str(body),
                      "distance": distance if isinstance(distance, (int, float)) else None,
                      "state": str(item.get("system_power_state") or "")})
    return found


def parse_stations(raw, commodity):
    """Spansh station search reply -> {system: best station}, only real stations that want at least MIN_DEMAND of the metal."""
    results = raw.get("results") if isinstance(raw, dict) else None
    best = {}
    for item in results or []:
        if not isinstance(item, dict):
            continue
        name, system = item.get("name"), item.get("system_name")
        if not name or not system or "carrier" in str(item.get("type") or "").lower():
            continue
        demand, price = None, 0
        for entry in item.get("market") or []:
            if isinstance(entry, dict) and str(entry.get("commodity")).lower() == commodity.lower():
                demand, price = entry.get("demand"), entry.get("sell_price") or 0
        if not isinstance(demand, (int, float)) or demand < MIN_DEMAND:
            continue
        row = {"station": str(name), "system": str(system), "material": commodity, "demand": int(demand),
               "price": int(price) if isinstance(price, (int, float)) else 0, "station_type": str(item.get("type") or "")}
        if system not in best or row["demand"] > best[system]["demand"]:
            best[system] = row
    return best


def combine(bodies, stations_by_commodity, limit=2):
    """Nearest system that has both a pristine metallic ring AND a market that wants a metal."""
    options = []
    for body in bodies:
        market = None
        for table in stations_by_commodity:
            row = table.get(body["system"])
            if row and (market is None or row["demand"] > market["demand"]):
                market = row
        if market is None:
            continue
        options.append(dict(market, body=body["body"], distance=body["distance"], state=body["state"],
                            tons=market["demand"]))
        if len(options) >= limit:
            break
    return options


def post_json(path, body, timeout=TIMEOUT_SECONDS):
    request = urllib.request.Request(BASE_URL + path, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"User-Agent": "Starling/1.0 (Elite Dangerous companion)",
                                              "Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as reply:
        return json.loads(reply.read().decode("utf-8"))


class MeritFinder:
    def __init__(self, settings=None, post=post_json, clock=time.monotonic, thread_factory=None):
        self.settings = settings
        self.post = post
        self.clock = clock
        self.thread_factory = thread_factory or (lambda target: threading.Thread(target=target, daemon=True, name="merit-finder"))
        self._cache = {}
        self._lock = threading.Lock()

    def enabled(self):
        return self.settings is None or bool(self.settings.get("mining.merit", True))

    def commodities(self):
        listed = self.settings.get("merit.commodities", None) if self.settings is not None else None
        names = [str(c).strip() for c in (listed or DEFAULT_COMMODITIES) if str(c).strip()]
        return names or list(DEFAULT_COMMODITIES)

    def power(self, state):
        """The Power from the dashboard if you chose one there, otherwise what the journal says you are pledged to."""
        chosen = str(self.settings.get("merit.power", "") or "").strip() if self.settings is not None else ""
        return chosen or str(getattr(state, "power", "") or "").strip()

    def lookup(self, system, power):
        """(options, ok). ok is False when Spansh could not be reached. Blocking: call from a thread."""
        key = (str(system).lower(), str(power).lower())
        now = self.clock()
        with self._lock:
            cached = self._cache.get(key)
            if cached and now - cached[0] < CACHE_SECONDS:
                return cached[1], True
        try:
            bodies = parse_bodies(self.post("/bodies/search", bodies_request(power, system)))
            systems = [b["system"] for b in bodies][:MAX_SYSTEMS]
            tables = []
            if systems:
                for commodity in self.commodities():
                    tables.append(parse_stations(self.post("/stations/search", stations_request(systems, commodity, system)),
                                                 commodity))
            options = combine([b for b in bodies if b["system"] in systems], tables)
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as error:
            log.warning("Merit mining search failed (%s)", error)
            return [], False
        except Exception:
            log.exception("Merit mining search crashed")
            return [], False
        with self._lock:
            self._cache[key] = (now, options)
        return options, True

    def lookup_async(self, system, power, done):
        def work():
            try:
                options, ok = self.lookup(system, power)
            except Exception:
                log.exception("Merit mining search crashed")
                options, ok = [], False
            try:
                done(options, ok)
            except Exception:
                log.exception("Merit mining answer crashed")
        self.thread_factory(work).start()
