"""
HER FAVOURITE SHIP.

Every time her mood goes UP (a good jump, a sale, a kind word...) the good points are credited to the ship you are flying.
When one ship has collected THRESHOLD points (20), that ship becomes her favourite. If another ship later collects more than
the favourite has, the favourite changes. She says so when it happens, makes a happier comment when you fly it, and tells you
if you ask "what's your favourite ship?".

Saved in data/favourite_ship.json, so it survives restarts.
"""

import json

from core import paths
from core.logger import get_logger
from core.ships import is_ship, ship_name

log = get_logger("favourite")

THRESHOLD = 20.0
MAX_SHIPS = 60                 # a sane limit on how many different ships we remember


class FavouriteShip:
    def __init__(self, state_provider, settings=None, say=None, path=None, persist=True, threshold=THRESHOLD):
        self.state_provider = state_provider
        self.settings = settings
        self.say = say                 # say(key, fields): speaks a line from the dialogue (set by the app)
        self.path = path or (paths.DATA_DIR / "favourite_ship.json")
        self.persist = persist
        self.threshold = float(threshold)
        self.points = {}               # ship code name -> good points
        self.labels = {}               # ship code name -> how she says it
        self.favourite = None
        self._load()
        self._publish()

    # ---- crediting points ----
    def add(self, points):
        """Called with every mood gain. Credits the ship you are flying."""
        state = self.state_provider()
        ship = str(getattr(state, "ship", "") or "").strip().lower()
        if not ship or points <= 0 or not is_ship(ship):        # the Nomad and the SRVs are vehicles, not ships
            return
        if ship not in self.points and len(self.points) >= MAX_SHIPS:
            return
        self.points[ship] = self.points.get(ship, 0.0) + float(points)
        self.labels[ship] = ship_name(getattr(state, "ship", None), getattr(state, "ship_model", None)) or self.labels.get(ship, ship)
        self._check(ship)
        self._save_soon()

    def _check(self, ship):
        mine = self.points.get(ship, 0.0)
        if mine < self.threshold or ship == self.favourite:
            return
        old = self.favourite
        if old is not None and mine <= self.points.get(old, 0.0):
            return
        self.favourite = ship
        self._publish()
        log.info("Her favourite ship is now the %s (%.1f good points)", self.labels.get(ship, ship), mine)
        if self.say is not None:
            fields = {"ship": self.labels.get(ship, ship), "old": self.labels.get(old, "") if old else ""}
            self.say("FavouriteShip_Changed" if old else "FavouriteShip_New", fields)

    # ---- asking ----
    def is_favourite(self, ship_code):
        return bool(self.favourite) and str(ship_code or "").strip().lower() == self.favourite

    def favourite_label(self):
        return self.labels.get(self.favourite, self.favourite) if self.favourite else None

    def points_for(self, ship_code):
        return self.points.get(str(ship_code or "").strip().lower(), 0.0)

    def _publish(self):
        try:
            state = self.state_provider()
        except AttributeError:
            return                           # the app has not made its game state yet; it is set again on the first good point
        if state is not None:
            try:
                state.favourite_ship = self.favourite
            except AttributeError:
                pass

    # ---- saving ----
    def _load(self):
        if not self.persist:
            return
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            self.points = {str(k): float(v) for k, v in (data.get("points") or {}).items()}
            self.labels = {str(k): str(v) for k, v in (data.get("labels") or {}).items()}
            for code in [c for c in self.points if not is_ship(c)]:       # an older file may have counted the Nomad: drop it
                self.points.pop(code, None)
                self.labels.pop(code, None)
            fav = data.get("favourite")
            if fav not in self.points:
                best = max(self.points, key=self.points.get) if self.points else None
                fav = best if best is not None and self.points[best] >= self.threshold else None
            self.favourite = fav
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, AttributeError):
            log.warning("Could not read %s", self.path, exc_info=True)

    def _save_soon(self):
        if not self.persist:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            with open(temp, "w", encoding="utf-8") as handle:
                json.dump({"points": {k: round(v, 2) for k, v in self.points.items()}, "labels": self.labels,
                           "favourite": self.favourite}, handle)
            temp.replace(self.path)
        except OSError:
            log.warning("Could not save her favourite ship", exc_info=True)
