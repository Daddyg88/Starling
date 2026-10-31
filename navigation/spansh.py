"""
Spansh: the free community route planner (spansh.co.uk) that works out neutron-star routes.

We ask it for a route and it sends back a list of WAYPOINTS: the neutron stars (and fuel stops) to aim for,
with the number of normal jumps between them. It works in two steps, because big routes take a few seconds:
    1. POST /api/route                (from, to, range, efficiency...)   -> a job number
    2. GET  /api/results/<job>        (ask again until it says "ok")     -> the route
System names are looked up with  GET /api/search/systems?q=<name>.

No account or key is needed. Only this file talks to the internet, so it is easy to check and to switch off.
Every problem becomes a SpanshError with a sentence she can say.
"""

import difflib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from core.secure_open import open_url

from core.logger import get_logger

log = get_logger("spansh")

BASE = "https://spansh.co.uk/api"
USER_AGENT = "Starling/0.9 (Elite Dangerous companion; neutron route plotting)"
SUBMIT_TIMEOUT = 20
POLL_TIMEOUT = 20
MAX_WAIT_SECONDS = 90


class SpanshError(Exception):
    pass


class Spansh:
    def __init__(self, opener=None, sleep=time.sleep, clock=time.monotonic):
        self._open = opener or open_url
        self.sleep = sleep
        self.clock = clock

    # ---- the one place that talks HTTP ----
    def _request(self, url, data=None, timeout=SUBMIT_TIMEOUT):
        request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
        try:
            with self._open(request, timeout=timeout) as reply:
                raw = reply.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            message = ""
            try:
                message = str(json.loads(error.read().decode("utf-8", "replace")).get("error", ""))
            except Exception:
                pass
            raise SpanshError(message or "Spansh answered with error %s." % error.code)
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            log.info("Could not reach Spansh: %s", error)
            raise SpanshError("I can't reach Spansh. Check your internet connection.")
        try:
            return json.loads(raw)
        except ValueError:
            raise SpanshError("Spansh sent a reply I couldn't read.")

    # ---- finding a system ----
    def find_system(self, name):
        """The proper spelling of a system. Exact match if there is one, else the closest. Raises if nothing is close."""
        name = " ".join(str(name or "").split())
        if not name:
            raise SpanshError("I didn't catch a destination.")
        answer = self._request("%s/search/systems?%s" % (BASE, urllib.parse.urlencode({"q": name})))
        names = [str(row.get("name") or "") for row in (answer.get("results") or []) if isinstance(row, dict)]
        names = [n for n in names if n]
        if not names:
            raise SpanshError("Spansh doesn't know a system called %s." % name)
        for candidate in names:
            if candidate.casefold() == name.casefold():
                return candidate
        best = max(names, key=lambda n: difflib.SequenceMatcher(None, n.casefold(), name.casefold()).ratio())
        if difflib.SequenceMatcher(None, best.casefold(), name.casefold()).ratio() < 0.6:
            raise SpanshError("I couldn't find a system like %s." % name)
        return best

    def coordinates(self, name):
        """(x, y, z) of a system if Spansh's search shows them, else None (the caller then treats the distance as unknown)."""
        name = " ".join(str(name or "").split())
        try:
            answer = self._request("%s/search/systems?%s" % (BASE, urllib.parse.urlencode({"q": name})))
        except SpanshError:
            return None
        for row in answer.get("results") or []:
            if isinstance(row, dict) and str(row.get("name") or "").casefold() == name.casefold():
                try:
                    return float(row["x"]), float(row["y"]), float(row["z"])
                except (KeyError, TypeError, ValueError):
                    return None
        return None

    # ---- the route ----
    def neutron_route(self, start, destination, jump_range, efficiency=60, supercharge=4, max_wait=MAX_WAIT_SECONDS):
        """A list of waypoints: [{"system", "neutron", "jumps", "distance_left"}, ...]. The first is where you are."""
        if not start:
            raise SpanshError("I don't know which system we're in yet.")
        form = urllib.parse.urlencode({
            "from": start, "to": destination, "range": "%.2f" % float(jump_range),
            "efficiency": int(efficiency), "supercharge_multiplier": 6 if int(supercharge) == 6 else 4,
        }).encode("ascii")
        job = self._request("%s/route" % BASE, data=form).get("job")
        if not job:
            raise SpanshError("Spansh didn't accept the route request.")
        deadline = self.clock() + max_wait
        polls = 0
        while self.clock() < deadline:
            data = self._request("%s/results/%s" % (BASE, urllib.parse.quote(str(job), safe="")), timeout=POLL_TIMEOUT)
            status = data.get("status")
            if status == "ok":
                return self._waypoints(data.get("result"))
            if status not in ("queued", "processing", "started"):
                raise SpanshError(str(data.get("error") or "Spansh couldn't plot that route."))
            polls += 1
            self.sleep(0.5 if polls <= 4 else 1.0)
        raise SpanshError("Spansh took too long. Try again in a moment.")

    @staticmethod
    def _waypoints(result):
        rows = result.get("system_jumps") if isinstance(result, dict) else None
        if not rows:
            raise SpanshError("Spansh found no route.")
        out = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("system"):
                continue
            out.append({"system": str(row["system"]), "neutron": bool(row.get("neutron_star")),
                        "jumps": int(row.get("jumps") or 0), "distance_left": float(row.get("distance_left") or 0)})
        if not out:
            raise SpanshError("Spansh found no route.")
        return out
