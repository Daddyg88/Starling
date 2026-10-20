"""
Keeps count of your mining session, so she can say what you have found and what is worth selling.
It only listens to the event bus; it never speaks by itself and never touches the game.
"""
import time

from mining import minerals

MINING_EVENTS = ("ProspectedAsteroid", "MiningRefined", "AsteroidCracked")
SESSION_GAP_SECONDS = 3 * 3600        # three quiet hours = a new mining session


class MiningTracker:
    def __init__(self, bus=None, clock=time.monotonic):
        self.bus = bus
        self.clock = clock
        self.reset()

    def reset(self):
        self.refined = {}             # game name -> tonnes
        self.prospected = 0
        self.cracked = 0
        self.motherlodes = 0
        self.last_refined = None      # game name of the newest refined mineral
        self.last_event = None

    def attach(self):
        if self.bus is not None:
            self.bus.subscribe("*", self.on_event)

    def on_event(self, event):
        name = event.name
        data = event.data or {}
        now = self.clock()
        if name in MINING_EVENTS or (name == "LaunchDrone" and "prospect" in str(data.get("Type", "")).lower()):
            if self.last_event is not None and now - self.last_event > SESSION_GAP_SECONDS:
                self.reset()
            self.last_event = now
        if name == "ProspectedAsteroid":
            self.prospected += 1
            if data.get("Motherlode"):
                self.motherlodes += 1
        elif name == "AsteroidCracked":
            self.cracked += 1
        elif name == "MiningRefined":
            key = data.get("Commodity") or minerals.normal(data.get("Material"))
            if key:
                self.refined[key] = self.refined.get(key, 0) + 1
                self.last_refined = key

    # ---- questions ----
    def total(self):
        return sum(self.refined.values())

    def ranked(self):
        """[(game name, tonnes)] best minerals first (top tier, then good, then the rest; most tonnes first)."""
        order = {"top": 0, "good": 1, "low": 2}
        return sorted(self.refined.items(), key=lambda kv: (order[minerals.tier(kv[0])], -kv[1], kv[0]))

    def best(self):
        ranked = self.ranked()
        return ranked[0] if ranked else None

    def best_text(self):
        """'Most valuable: 6 tonnes of Platinum.' (empty when nothing is refined)."""
        best = self.best()
        if not best:
            return ""
        key, tonnes = best
        return "Best find: %d %s of %s." % (tonnes, "tonne" if tonnes == 1 else "tonnes", minerals.spoken(key))

    def to_sell(self):
        """The mineral she should look up by default: the best one, otherwise the newest one."""
        best = self.best()
        if best and minerals.tier(best[0]) != "low":
            return best[0]
        return self.last_refined or (best[0] if best else None)

    def is_mining(self, seconds=600):
        return self.last_event is not None and self.clock() - self.last_event < seconds
