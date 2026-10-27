"""
A tiny client for Void Compass's Local API. Plain HTTP on this PC, so nothing to install.

In Void Compass: Settings > Integrations > Local API > switch it on. Then it answers at
http://127.0.0.1:7380/api/v1 (the port can be changed there; put the same number in Starling's Controls page).

Every problem becomes a VoidError with a short `kind`, which the runner turns into a spoken sentence:
    offline    Void Compass isn't running, or its Local API is off (or the port is wrong)
    forbidden  "Allow control" is switched off in Void Compass, so it only lets us read
    conflict   Void Compass understood but couldn't do it right now (message says why)
    missing    this version of Void Compass doesn't have that overlay
    failed     anything else
"""

import json
import time
import urllib.error
import urllib.request

from core.logger import get_logger

log = get_logger("voidcompass")

HOST = "127.0.0.1"          # never anything but this PC
DEFAULT_PORT = 7380
TIMEOUT_SECONDS = 3.0


class VoidError(Exception):
    def __init__(self, kind, message=""):
        super().__init__(message or kind)
        self.kind = kind
        self.message = message


class VoidCompass:
    def __init__(self, port=DEFAULT_PORT, timeout=TIMEOUT_SECONDS, opener=None):
        self.port = int(port)
        self.timeout = timeout
        self._open = opener or urllib.request.urlopen

    @property
    def base(self):
        return "http://%s:%d/api/v1" % (HOST, self.port)

    # ---- the one place that talks HTTP ----
    def _call(self, method, path, body=None, timeout=None):
        data = None if body is None and method == "GET" else json.dumps(body or {}).encode("utf-8")
        request = urllib.request.Request(self.base + path, data=data, method=method,
                                         headers={"Content-Type": "application/json"})
        try:
            with self._open(request, timeout=timeout or self.timeout) as reply:
                raw = reply.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            raise self._http_error(error)
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            now = time.monotonic()
            if now - getattr(self, "_last_offline_log", -1e9) > 600:       # say it once in a while, not every 12 seconds
                self._last_offline_log = now
                log.info("Void Compass not reachable on port %s: %s (further messages hidden for 10 minutes)", self.port, error)
            raise VoidError("offline", "I can't reach Void Compass.")
        try:
            return json.loads(raw) if raw.strip() else {}
        except ValueError:
            raise VoidError("failed", "Void Compass sent something I couldn't read.")

    @staticmethod
    def _http_error(error):
        message = ""
        try:
            message = str(json.loads(error.read().decode("utf-8", "replace")).get("error", {}).get("message", ""))
        except Exception:
            pass
        kind = {403: "forbidden", 404: "missing", 409: "conflict", 503: "offline", 504: "conflict"}.get(error.code, "failed")
        return VoidError(kind, message or "Void Compass answered %s." % error.code)

    # ---- what we need ----
    def ping(self):
        self._call("GET", "/ping")
        return True

    def overlays(self):
        """{"hidden": bool, "overlays": [{"id", "name", "enabled", "shown", ...}]}"""
        answer = self._call("GET", "/overlays")
        if not isinstance(answer, dict):
            raise VoidError("failed", "Void Compass sent something I couldn't read.")
        return answer

    def set_enabled(self, overlay_id, enabled):
        return self._call("POST", "/overlays/%s" % overlay_id, {"enabled": bool(enabled)})

    def hide_all(self, hidden):
        return self._call("POST", "/overlays/%s" % ("hide-all" if hidden else "show-all"))

    # ---- the Watcher and his voice ----
    def events(self, since=0, types="voice,thought", wait=0):
        """{"seq": n, "events": [...]}. With wait > 0 Void Compass holds the call open until something happens."""
        path = "/events?since=%d&types=%s&wait=%d" % (int(since), types, int(wait))
        return self._call("GET", path, timeout=self.timeout + int(wait) + 5)

    def now_seq(self):
        return int(self._call("GET", "/events?limit=1").get("seq", 0))

    def voice(self):
        """{"enabled", "installed", "ready", "speaking"}"""
        return self._call("GET", "/voice")

    def voice_say(self, text):
        return self._call("POST", "/voice/say", {"text": str(text)[:400]})

    def voice_hush(self, seconds=12):
        """Newer Void Compass: keep the Watcher quiet for a while (POST /voice/hush) because our own voice assistant is talking."""
        return self._call("POST", "/voice/hush", {"seconds": int(seconds), "duration": int(seconds)})

    def watcher_answer(self, answer):
        """Newer Void Compass: answer a question the Watcher asked (POST /watcher/answer), the same as a Stream Deck button."""
        return self._call("POST", "/watcher/answer", {"answer": answer})

    def voice_stop(self):
        return self._call("POST", "/voice/stop")
