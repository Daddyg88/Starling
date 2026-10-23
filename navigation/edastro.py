"""
EDAstro (edastro.com): a community map of points of interest (galactic landmarks, nav markers, DSSA-style support places).

Used only for the "emergency protocol": when Spansh does not know the system you are in, she asks EDAstro for the
nearest landmark to your coordinates (the journal gives them), then plots a course there in the game itself.
EDAstro allows 100 requests per 15 minutes, so she asks sparingly. Only this file talks to EDAstro.

    GET https://edastro.com/gec/json/nearest/<x>/<y>/<z>[/<minimum rating>]   -> the single nearest point of interest
"""

import json
import math
import urllib.error
import urllib.request

from core.logger import get_logger

log = get_logger("edastro")

BASE = "https://edastro.com/gec/json"
USER_AGENT = "Starling/0.32 (Elite Dangerous companion; emergency route finder)"
TIMEOUT = 15


class EdAstroError(Exception):
    pass


def distance(a, b):
    return math.sqrt(sum((float(p) - float(q)) ** 2 for p, q in zip(a, b)))


class EdAstro:
    def __init__(self, opener=None):
        self._open = opener or urllib.request.urlopen

    def nearest(self, position, min_rating=None):
        """The nearest point of interest: {"system", "poi", "coords", "rating"} or None. Raises EdAstroError if EDAstro can't be reached."""
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
