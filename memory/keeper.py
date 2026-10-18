"""
THE KEEPER - watches the game events and writes down the moments worth remembering.
It only listens; it never presses a key or speaks. Anything wrong inside it is logged and ignored.

What it keeps: your longest jump, your biggest organic sale and exploration sale, every time you were destroyed,
big missions, the first time you sample each species, jumps made, missions done and hours together.
"""
import time

from core.event_bus import ALL_EVENTS
from core.logger import get_logger

log = get_logger("memory")

BIG_MISSION = 5_000_000


def credits(value):
    value = int(value or 0)
    if value >= 1_000_000:
        return ("%.1f" % (value / 1_000_000)).rstrip("0").rstrip(".") + " million credits"
    return format(value, ",") + " credits"


class MemoryKeeper:
    def __init__(self, bus, store, settings, state_provider=None, clock=time.monotonic):
        self.bus = bus
        self.store = store
        self.settings = settings
        self.state_provider = state_provider or (lambda: None)
        self.clock = clock
        self.started = clock()
        self._hours_saved = False

    def attach(self):
        self.bus.subscribe(ALL_EVENTS, self.on_event)

    def enabled(self):
        return bool(self.settings.get("memory.enabled", True))

    def _system(self, data):
        state = self.state_provider()
        return (data or {}).get("StarSystem") or getattr(state, "system", None)

    def on_event(self, event):
        try:
            if event.name == "app.stopping":
                self.save_hours()
                return
            if not self.enabled():
                return
            handler = getattr(self, "_on_" + event.name, None)
            if handler is not None:
                handler(dict(event.data or {}))
        except Exception:
            log.exception("The memory keeper could not note %s", getattr(event, "name", "?"))

    def save_hours(self):
        """Add the time of this play session to 'hours together' (once)."""
        if self._hours_saved or not self.enabled():
            return
        self._hours_saved = True
        hours = max(0.0, (self.clock() - self.started) / 3600.0)
        self.store.increment("hours_together", round(hours, 4))

    # ---- one small method per event ----
    def _on_Died(self, data):
        killer = data.get("KillerName")
        system = self._system(data)
        text = "You were destroyed" + (" by %s" % killer if killer else "") + (" in %s" % system if system else "")
        self.store.add("death", text, system, importance=2)
        self.store.increment("times_destroyed")

    def _on_FSDJump(self, data):
        self.store.increment("systems_visited")          # counts jumps made
        dist, system = data.get("JumpDist"), data.get("StarSystem")
        if isinstance(dist, (int, float)) and dist > 0 and system:
            self.store.set_record("longest_jump", "your longest jump, %.1f light years, into %s" % (dist, system), dist, system)

    def _on_SellOrganicData(self, data):
        total = data.get("TotalValue") or 0
        if total > 0:
            self.store.set_record("biggest_organic_sale", "your biggest biology sale, %s" % credits(total), total,
                                  self._system(data))

    def _sold_exploration(self, data):
        total = data.get("TotalEarnings") or 0
        if total > 0:
            self.store.set_record("biggest_exploration_sale", "your biggest exploration sale, %s" % credits(total), total,
                                  self._system(data))

    _on_SellExplorationData = _sold_exploration
    _on_MultiSellExplorationData = _sold_exploration

    def _on_MissionCompleted(self, data):
        self.store.increment("missions_completed")
        reward = data.get("Reward") or 0
        name = data.get("LocalisedName")
        if isinstance(reward, (int, float)) and reward >= BIG_MISSION and name:
            self.store.add("big_mission", "a mission worth %s: %s" % (credits(reward), name), self._system(data), importance=2)

    def _on_ScanOrganic(self, data):
        species = data.get("Species_Localised") or data.get("Genus_Localised")
        if species and str(data.get("ScanType", "")).lower() == "log":
            self.store.add("first_species", "the first time you sampled %s" % species, self._system(data))
