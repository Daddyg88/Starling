"""
Material storage callouts: "you are 82 percent full on iron".

Collecting materials can happen in bursts, so she is careful:
  * She waits a few seconds after the last pickup, then looks at everything you just collected as ONE batch.
  * A material is only mentioned when it is at least MIN_PERCENT full (setting, default 25) and it has risen by at least STEP points
    since she last mentioned it (so 82, then 92, not every single pickup). Hitting 100 is always worth a word.
  * One line per batch: the fullest one or two materials (more than two = "several materials are filling up, the fullest is ...").
  * At least COOLDOWN seconds between two callouts, each material at most once per MATERIAL_COOLDOWN, and at most MAX_PER_WINDOW
    callouts in any WINDOW seconds. A full store is allowed to go over those limits only once per material per FULL_COOLDOWN.
Her words: voicepacks/default/materials.json.
"""

import threading
import time
from collections import deque

from core.logger import get_logger
from journal import materials

log = get_logger("matfill")

BATCH_SECONDS = 4.0
STEP = 10
COOLDOWN = 25.0
MATERIAL_COOLDOWN = 120.0
FULL_COOLDOWN = 300.0
WINDOW = 600.0
MAX_PER_WINDOW = 5


class MaterialFill:
    def __init__(self, bus, settings, narrator, state_provider, clock=time.monotonic, timer_factory=None):
        self.bus = bus
        self.settings = settings
        self.narrator = narrator
        self.state_provider = state_provider
        self.clock = clock
        self.timer_factory = timer_factory or self._real_timer
        self._batch = []                 # material names collected since the last callout decision
        self._timer = None
        self._said_at = {}               # name -> time of the last callout
        self._said_pct = {}              # name -> percent at the last callout
        self._full_at = {}               # name -> time we last said it was full
        self._recent = deque()           # times of the last callouts
        self._lock = threading.Lock()

    @staticmethod
    def _real_timer(seconds, function):
        timer = threading.Timer(seconds, function)
        timer.daemon = True
        return timer

    def attach(self):
        self.bus.subscribe("MaterialCollected", self.on_collected)

    def detach(self):
        self.bus.unsubscribe("MaterialCollected", self.on_collected)

    def _on(self):
        return bool(self.settings.get("materials.fill_callout", True))

    def _min_percent(self):
        try:
            return max(0, min(100, int(float(str(self.settings.get("materials.fill_min_percent", 25)).strip()))))
        except (TypeError, ValueError):
            return 25

    def on_collected(self, event):
        if not self._on():
            return
        name = (getattr(event, "data", None) or {}).get("Name")
        if not name:
            return
        with self._lock:
            if name not in self._batch:
                self._batch.append(name)
            if self._timer is not None:
                self._timer.cancel()
            self._timer = self.timer_factory(BATCH_SECONDS, self.flush)
            self._timer.start()

    def flush(self):
        """Decide what to say about the batch (called by the timer; tests call it directly)."""
        with self._lock:
            batch, self._batch, self._timer = self._batch, [], None
        try:
            self._decide(batch)
        except Exception:
            log.exception("The material callout failed")

    def _decide(self, batch):
        state = self.state_provider()
        now = self.clock()
        minimum = self._min_percent()
        candidates, full = [], []
        for name in batch:
            pct = materials.percent(state, name)
            if pct is None:
                continue
            last = self._said_pct.get(name)
            if last is not None and pct < last:
                self._said_pct[name] = pct               # you spent some: start counting from here
                continue
            if pct >= 100:
                if now - self._full_at.get(name, -1e9) >= FULL_COOLDOWN:
                    full.append((pct, name))
                continue
            if pct < minimum:
                continue
            if last is not None and pct < last + STEP:
                continue
            if now - self._said_at.get(name, -1e9) < MATERIAL_COOLDOWN:
                continue
            candidates.append((pct, name))
        if full:
            pct, name = full[0]
            self._full_at[name] = now
            self._said_at[name], self._said_pct[name] = now, pct
            self._remember(now)
            self.narrator.say("MaterialFill_Full", {"Material": materials.display_name(name), "Percent": pct})
            return
        if not candidates:
            return
        self._recent_trim(now)
        if self._recent and now - self._recent[-1] < COOLDOWN:
            return
        if len(self._recent) >= MAX_PER_WINDOW:
            return
        candidates.sort(reverse=True)
        fields = {"Material": materials.display_name(candidates[0][1]), "Percent": candidates[0][0], "Count": len(candidates)}
        if len(candidates) == 1:
            key = "MaterialFill_One"
        elif len(candidates) == 2:
            key = "MaterialFill_Two"
            fields.update({"Material2": materials.display_name(candidates[1][1]), "Percent2": candidates[1][0]})
        else:
            key = "MaterialFill_Many"
        for pct, name in candidates[:2] if len(candidates) <= 2 else candidates:
            self._said_at[name], self._said_pct[name] = now, pct
        self._remember(now)
        self.narrator.say(key, fields)

    def _recent_trim(self, now):
        while self._recent and now - self._recent[0] > WINDOW:
            self._recent.popleft()

    def _remember(self, now):
        self._recent_trim(now)
        self._recent.append(now)
