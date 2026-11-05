"""
EDAstro (edastro.com): a community map of points of interest (galactic landmarks, nav markers, DSSA-style support places).

Used only for the "emergency protocol": when Spansh does not know the system you are in, she asks EDAstro for the
nearest landmark to your coordinates (the journal gives them), then plots a course there in the game itself.
EDAstro allows 100 requests per 15 minutes, so she asks sparingly. Only this file talks to EDAstro.

    GET https://edastro.com/gec/json/nearest/<x>/<y>/<z>[/<minimum rating>]   -> the single nearest point of interest
    GET https://edastro.com/gec/json/combined                                 -> every point of interest (GEC + GMP, with coordinates)

The "nearest" answer turned out to be unreliable far from the bubble (it kept answering "Sol, 12,000 light years away"), so when
a cache file is given she downloads the whole list once a day, keeps it on disk, and finds the truly nearest place herself.
"""

import json
import math
import time
from pathlib import Path
import urllib.error
import urllib.request
from core.secure_open import open_url

from core.logger import get_logger

log = get_logger("edastro")

BASE = "https://edastro.com/gec/json"
USER_AGENT = "Starling/0.32 (Elite Dangerous companion; emergency route finder)"
TIMEOUT = 15


class EdAstroError(Exception):
    pass


def distance(a, b):
    return math.sqrt(sum((float(p) - float(q)) ** 2 for p, q in zip(a, b)))


LIST_URLS = (BASE + "/combined", BASE + "/all")
LIST_MAX_AGE = 24 * 3600
LIST_MAX_BYTES = 12_000_000


class EdAstro:
    def __init__(self, opener=None, cache_file=None, clock=time.time):
        self._open = opener or open_url
        self.cache_file = Path(cache_file) if cache_file else None
        self.clock = clock
        self.pois = []
        self.loaded_at = 0.0
        self._loaded = False

    # ---- the whole list, kept on disk ----
    def _load_cache(self):
        self._loaded = True
        try:
            data = json.loads(self.cache_file.read_text(encoding="utf-8")) if self.cache_file and self.cache_file.exists() else {}
        except (OSError, ValueError):
            data = {}
        self.pois = [p for p in data.get("pois", []) if isinstance(p, dict) and p.get("system") and p.get("coords")]
        self.loaded_at = float(data.get("at") or 0)

    def _download_list(self):
        for url in LIST_URLS:
            try:
                request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with self._open(request, timeout=TIMEOUT * 2) as reply:
                    raw = reply.read(LIST_MAX_BYTES).decode("utf-8", "replace")
                items = json.loads(raw)
            except (urllib.error.URLError, OSError, TimeoutError, ValueError) as error:
                log.info("Could not read the EDAstro list %s: %s", url, error)
                continue
            if isinstance(items, dict):
                items = items.get("pois") or items.get("data") or list(items.values())
            found, seen = [], set()
            for item in items if isinstance(items, list) else []:
                place = self._parse(item)
                if not place or not place.get("coords"):
                    continue
                key = (place["system"].casefold(), str(place.get("poi")).casefold())
                if key not in seen:
                    seen.add(key)
                    found.append(place)
            if found:
                return found
        return None

    def refresh(self, force=False):
        """True when we have a list (fresh, or the old one if EDAstro can't be reached)."""
        if self.cache_file is None:
            return False
        if not self._loaded:
            self._load_cache()
        if self.pois and not force and self.clock() - self.loaded_at < LIST_MAX_AGE:
            return True
        found = self._download_list()
        if found:
            self.pois, self.loaded_at = found, self.clock()
            try:
                self.cache_file.parent.mkdir(parents=True, exist_ok=True)
                self.cache_file.write_text(json.dumps({"at": self.loaded_at, "pois": found}), encoding="utf-8")
            except OSError:
                log.warning("Could not save the EDAstro list", exc_info=True)
        return bool(self.pois)

    def nearest_local(self, position, min_rating=None):
        """The truly nearest place in the downloaded list (or None when there is no list)."""
        if not self.refresh():
            return None
        best = None
        for place in self.pois:
            if min_rating:
                try:
                    if float(place.get("rating") or 0) < float(min_rating):
                        continue
                except (TypeError, ValueError):
                    continue
            d = distance(position, place["coords"])
            if best is None or d < best[0]:
                best = (d, place)
        return dict(best[1]) if best else None

    def nearest_many(self, position, count=8):
        """The closest places in the downloaded list, nearest first (empty when there is no list)."""
        if not self.refresh():
            return []
        ranked = sorted(self.pois, key=lambda place: distance(position, place["coords"]))
        return [dict(place) for place in ranked[:count]]

    def nearest(self, position, min_rating=None):
        """The nearest point of interest: {"system", "poi", "coords", "rating"} or None. Raises EdAstroError if EDAstro can't be reached."""
        local = self.nearest_local(position, min_rating)
        if local is not None:
            return local
        x, y, z = (float(v) for v in position)
        url = "%s/nearest/%.2f/%.2f/%.2f" % (BASE, x, y, z) + ("/%d" % int(min_rating) if min_rating else "")
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with self._open(request, timeout=TIMEOUT) as reply:
                raw = reply.read().decode("utf-8", "replace")
            data = json.loads(raw)
        except urllib.error.HTTPError as error:
            raise EdAstroError("EDAstro answered with error %s." % error.code)
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            log.info("Could not reach EDAstro: %s", error)
            raise EdAstroError("I can't reach EDAstro. Check your internet connection.")
        except ValueError:
            raise EdAstroError("EDAstro sent a reply I couldn't read.")
        return self._parse(data)

    @staticmethod
    def _parse(data):
        if isinstance(data, list):
            data = data[0] if data else None
        if not isinstance(data, dict) or data.get("error"):
            return None
        system = ""
        for key in ("galMapSearch", "system", "systemName", "system_name", "name"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                system = value.strip()
                break
        if not system:
            return None
        coords = data.get("coordinates") or data.get("coords")
        if not (isinstance(coords, (list, tuple)) and len(coords) == 3 and all(isinstance(c, (int, float)) for c in coords)):
            coords = None
        poi = data.get("name") if isinstance(data.get("name"), str) else system
        return {"system": system, "poi": poi, "coords": coords, "rating": data.get("rating")}
