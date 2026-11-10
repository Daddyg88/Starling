"""Red alert: once the target ship has been fully scanned, she picks its power plant as the sub target by herself.

It watches the journal's ShipTargeted lines. The game writes one with ScanStage 3 when the scan of a locked ship is complete. If red alert is on,
and that line is for the ship itself (no sub target picked yet), she runs the same thing as saying "target power plant": it presses YOUR Next
Subsystem key (it never changes a key binding) and checks the journal after each press until the power plant is selected.

She does it once per ship, so if you pick another part yourself she leaves it alone, and she does nothing in supercruise, on foot or docked.
"""

import logging
import threading
import time

log = logging.getLogger("starling.autosub")

COOLDOWN_SECONDS = 4.0          # never twice in a row for a flickering target


class AutoSubTarget:
    def __init__(self, settings, runner_provider, red_alert_provider, state_provider, clock=time.monotonic, start=None):
        self.settings = settings
        self.runner_provider = runner_provider
        self.red_alert_provider = red_alert_provider
        self.state_provider = state_provider
        self.clock = clock
        self.start = start or self._start_thread        # tests pass a function that runs the job at once
        self._done = None                               # the ship she already did this for
        self._last = -999.0
        self._busy = False

    def on_entry(self, entry, silent):
        if silent or entry.get("event") != "ShipTargeted":
            return
        if not entry.get("TargetLocked", True):
            self._done = None                           # the lock was lost: the next ship (or the same one again) is new
            return
        if not self.settings.get("red_alert.auto_power_plant", True):
            return
        red = self.red_alert_provider()
        if not red or not getattr(red, "active", False):
            return
        if int(entry.get("ScanStage") or 0) < 3:
            return                                      # the scan is not finished: the power plant is not known yet
        if any(str(key).lower() == "subsystem" and value for key, value in entry.items()):
            return                                      # a part is already picked (by you, or by her a moment ago)
        key = (entry.get("Ship"), entry.get("PilotName"))
        if key == self._done or self._busy:
            return
        state = self.state_provider()
        if state is not None and (getattr(state, "in_supercruise", False) or getattr(state, "docked", False)
                                  or getattr(state, "on_foot", False)):
            return
        now = self.clock()
        if now - self._last < COOLDOWN_SECONDS:
            return
        self._done, self._last, self._busy = key, now, True
        self.start(self._run)

    def _run(self):
        try:
            runner = self.runner_provider()
            if runner is None:
                return
            log.info("Red alert: the target is scanned, selecting its power plant")
            runner.run_text("target power plant", speak=False, speak_unknown=False, auto=True)
        except Exception:
            log.exception("Red alert could not select the power plant")
        finally:
            self._busy = False

    @staticmethod
    def _start_thread(job):
        threading.Thread(target=job, name="auto-subtarget", daemon=True).start()
