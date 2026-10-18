"""
The RouteFollower: keeps track of your neutron route while you fly it.

A Spansh route is a list of WAYPOINTS (mostly neutron stars). Between two waypoints you make several normal
jumps along the in-game route. So the job is:
    * remember the route (data/neutron_route.json, so it survives a restart),
    * every time you arrive anywhere, check whether it was a waypoint, and if so
    * copy the NEXT waypoint's name to the Windows clipboard, so you can paste it into the galaxy map search,
    * and tell you (briefly) what is next.

Elite does not let any program plot a route inside the game, so pasting into the galaxy map is still yours.
"""

import json
import os
import subprocess
import threading

from core import paths
from core.logger import get_logger

log = get_logger("route")

AUTO_PLOT_DELAY_SECONDS = 3.0       # after the route is first plotted, or after arriving at a fuel stop
BOOST_PLOT_DELAY_SECONDS = 4.0      # after a neutron supercharge, before the galaxy map macro starts
# Hands-free plotting is skipped while: jumping, low fuel, overheating, in danger, interdicted.
# (Weapons out and the FSD charging are fine: you often fly with weapons out, and you may start charging at once.)
UNSAFE_BITS = (19, 20, 22, 23, 30)
SPEAK_DELAY_SECONDS = 6.0           # after an arrival, so she finishes her arrival line first


def copy_to_clipboard(text):
    """Put text on the Windows clipboard (uses Windows' own clip.exe). True if it worked."""
    if os.name != "nt" or not text:
        return False
    try:
        subprocess.run(["clip"], input=text.encode("cp1252", "replace"), check=True, timeout=5,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except (OSError, subprocess.SubprocessError):
        log.exception("Could not copy to the clipboard")
        return False


class RouteFollower:
    def __init__(self, bus, settings, narrator=None, state_provider=None, save_path=None, copier=copy_to_clipboard,
                 schedule=None):
        self.bus = bus
        self.settings = settings
        self.narrator = narrator
        self.state_provider = state_provider or (lambda: None)
        self.save_path = save_path or (paths.DATA_DIR / "neutron_route.json")
        self.copier = copier
        self.schedule = schedule or self._real_schedule
        self.auto_plot = None           # set by the app: a function that runs the galaxy map macro
        self._auto_for = None           # the waypoint we already auto-plotted, so it happens once per waypoint
        self.waypoints = []
        self.index = 0                  # the waypoint we are heading for
        self.destination = ""
        self.jumps_left = 0             # normal jumps to the next waypoint
        self._lock = threading.RLock()
        self.load()

    # ---- wiring ----
    def attach(self):
        self.bus.subscribe("FSDJump", self.on_jump)
        self.bus.subscribe("JetConeBoost", self.on_boost)

    def detach(self):
        self.bus.unsubscribe("FSDJump", self.on_jump)
        self.bus.unsubscribe("JetConeBoost", self.on_boost)

    @staticmethod
    def _real_schedule(seconds, function):
        timer = threading.Timer(seconds, function)
        timer.daemon = True
        timer.start()

    # ---- the route ----
    @property
    def active(self):
        return bool(self.waypoints) and self.index < len(self.waypoints)

    def next_waypoint(self):
        return self.waypoints[self.index] if self.active else None

    def set_route(self, waypoints, destination, here=None):
        """Start following. Waypoints that are the system we are already in are skipped."""
        with self._lock:
            self.waypoints = list(waypoints)
            self.destination = destination
            self.index = 0
            self._auto_for = None
            while (self.index < len(self.waypoints) and here
                   and self.waypoints[self.index]["system"].casefold() == str(here).casefold()):
                self.index += 1
            self.jumps_left = self.waypoints[self.index]["jumps"] if self.active else 0
            self.save()

    def clear(self):
        with self._lock:
            self.waypoints, self.index, self.destination, self.jumps_left = [], 0, "", 0
            self._auto_for = None
            self.save()

    def stops_left(self):
        return sum(1 for w in self.waypoints[self.index:] if w["neutron"])

    def total_jumps_left(self):
        return self.jumps_left + sum(w["jumps"] for w in self.waypoints[self.index + 1:])

    def copy_next(self):
        waypoint = self.next_waypoint()
        if waypoint is None or not self.settings.get("neutron.clipboard", True):
            return False
        return bool(self.copier(waypoint["system"]))

    # ---- arriving somewhere ----
    def on_jump(self, event):
        system = str((event.data or {}).get("StarSystem") or "")
        if not system or not self.active:
            return
        with self._lock:
            found = next((i for i in range(self.index, len(self.waypoints))
                          if self.waypoints[i]["system"].casefold() == system.casefold()), None)
            if found is None:
                self.jumps_left = max(0, self.jumps_left - 1)
                return
            reached = self.waypoints[found]
            self.index = found + 1
            arrived = not self.active
            self.jumps_left = self.waypoints[self.index]["jumps"] if self.active else 0
            self.save()
        if arrived:
            self._tell("RouteArrived", destination=self.destination)
            self.clear()
            return
        self.copy_next()
        key = "RouteNeutronNext" if reached["neutron"] else "RouteNext"
        self.schedule(SPEAK_DELAY_SECONDS, lambda: self._tell(key, **self.fields()))
        if not reached["neutron"]:
            self.maybe_auto_plot()          # a fuel stop: nothing to supercharge, so go straight on

    # ---- hands-free plotting (the galaxy map macro) ----
    def on_boost(self, event):
        """You just got your neutron supercharge: plot the next waypoint 4 seconds later, if you've asked for that."""
        self.maybe_auto_plot(BOOST_PLOT_DELAY_SECONDS, "supercharge")

    def maybe_auto_plot(self, delay=None, reason="route"):
        if not self.settings.get("neutron.auto_plot", False):
            log.info("Not plotting after the %s: 'Plot each waypoint in the galaxy map for me' is off", reason)
            return False
        if not self.active:
            return False
        if self.auto_plot is None:
            log.warning("Not plotting after the %s: the galaxy map macro is not connected (voice commands off?)", reason)
            return False
        if self._auto_for == self.index:
            return False
        state = self.state_provider()
        flags = getattr(state, "status_flags", 0) if state is not None else 0
        blocked = [bit for bit in UNSAFE_BITS if (flags >> bit) & 1]
        if blocked:
            log.info("Not plotting after the %s: the game says it is not a good moment (status bits %s)", reason, blocked)
            return False
        self._auto_for = self.index
        log.info("Plotting the next waypoint in %.0f seconds (after the %s)", delay or AUTO_PLOT_DELAY_SECONDS, reason)
        self.schedule(delay or AUTO_PLOT_DELAY_SECONDS, self.auto_plot)
        return True

    def fields(self):
        waypoint = self.next_waypoint() or {}
        return {"next": waypoint.get("system", ""), "jumps": self.jumps_left, "stops": self.stops_left(),
                "left": self.total_jumps_left(), "destination": self.destination,
                "clip": " It's on your clipboard." if self.settings.get("neutron.clipboard", True) else ""}

    def _tell(self, key, **fields):
        if self.narrator is not None and self.settings.get("neutron.announce", True):
            self.narrator.say(key, fields)

    # ---- remembering ----
    def save(self):
        data = {"destination": self.destination, "index": self.index, "waypoints": self.waypoints,
                "jumps_left": self.jumps_left}
        try:
            self.save_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = str(self.save_path) + ".tmp"
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(data, handle)
            os.replace(temporary, self.save_path)
        except OSError:
            log.exception("Could not save the route")

    def load(self):
        try:
            with open(self.save_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            self.waypoints = [w for w in data.get("waypoints", []) if isinstance(w, dict) and w.get("system")]
            self.index = int(data.get("index", 0))
            self.destination = str(data.get("destination", ""))
            self.jumps_left = int(data.get("jumps_left", 0))
        except (OSError, ValueError, TypeError):
            self.waypoints, self.index, self.destination, self.jumps_left = [], 0, "", 0
