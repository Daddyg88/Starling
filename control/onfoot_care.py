"""
On-foot care: uses a medical pack when your health is low, an energy cell when your shields are gone, and tells you when you
throw your LAST grenade of a type.

What the game really tells her (and what it does not):
  * Health 0 to 1 is in Status.json, so "20% or below" is real.
  * SUIT ENERGY is not in the game's manual for Status.json. She looks for a field with the usual names (SuitEnergy, Energy...)
    and uses the energy cell at 20% or lower when it exists. Without one she falls back to the first loss of health (damage hits
    shields first, so that is when the shields are gone). The log says which she found.
  * Backpack.json lists your item counts. When a grenade type goes from 1 to 0 while you hold a weapon, that was the last one.
  * AMMO is not in any file, so a low ammo callout is not possible. (She cannot see it, so she says nothing rather than guess.)
Each helper has its own switch on the On foot page. Nothing is pressed unless your backpack has one (when she can read it).
"""

import time

from core.logger import get_logger
from control.auto_shields import on_foot, weapon_in_hand
from journal import backpack

log = get_logger("onfootcare")

HEALTH_ACTION = "HumanoidHealthPack"
BATTERY_ACTION = "HumanoidBattery"
HEALTH_AT = 0.20
ENERGY_AT = 0.20
HEALTH_COOLDOWN = 6.0
BATTERY_COOLDOWN = 25.0
HURT_DROP = 0.02


class OnFootCare:
    def __init__(self, settings, book, sender, narrator, folder_provider, clock=time.monotonic):
        self.settings = settings
        self.book = book
        self.sender = sender
        self.narrator = narrator
        self.folder_provider = folder_provider
        self.clock = clock
        self._health = None
        self._last_health = None
        self._armed = False
        self._last = {}               # what -> time of the last press
        self._counts = None           # last Backpack.json counts
        self._mtime = None
        self.last_result = ""

    def _on(self, key, default=False):
        return bool(self.settings.get(key, default))

    def check(self, state):
        """Called after every Status.json read."""
        if not on_foot(state):
            self._health, self._last_health, self._armed = None, None, False
            self._counts, self._mtime = None, None          # a fresh look next trip (so a transfer is not "a throw")
            return
        health = getattr(state, "health", None)
        armed = weapon_in_hand(getattr(state, "selected_weapon", ""))
        counts = self._read_backpack()
        if isinstance(health, (int, float)):
            if self._on("onfoot.auto_health") and health <= HEALTH_AT:
                self._use(HEALTH_ACTION, "health", ("healthpack", "medkit", "medical"), HEALTH_COOLDOWN, "OnFootMedpack")
            self._health = health
        if self._on("onfoot.auto_battery"):
            energy = getattr(state, "suit_energy", None)
            if isinstance(energy, (int, float)):
                if energy <= ENERGY_AT:                             # the real suit energy, when the game gives it
                    self._use(BATTERY_ACTION, "battery", ("energycell", "battery"), BATTERY_COOLDOWN, "OnFootBattery")
            elif (isinstance(health, (int, float)) and self._last_health is not None and health < 1.0
                  and self._last_health - health >= HURT_DROP):
                self._use(BATTERY_ACTION, "battery", ("energycell", "battery"), BATTERY_COOLDOWN, "OnFootBattery")
        if isinstance(health, (int, float)):
            self._last_health = health
        if self._on("onfoot.last_grenade_callout", True) and counts is not None:
            self._grenades(self._previous, counts, armed)
        self._armed = armed

    _previous = None

    def _read_backpack(self):
        """Counts from Backpack.json, re-read only when the file changed. Remembers the old counts in self._previous."""
        folder = self.folder_provider()
        if not folder:
            return self._counts
        try:
            from pathlib import Path
            mtime = (Path(folder) / "Backpack.json").stat().st_mtime_ns
        except OSError:
            return self._counts
        if mtime == self._mtime:
            self._previous = self._counts
            return self._counts
        new = backpack.read_counts(folder)
        self._previous = self._counts if self._mtime is not None else new      # the first read is a baseline, not a change
        self._mtime = mtime
        self._counts = new
        if new is not None:
            log.info("Backpack: %s", ", ".join("%s x%d" % kv for kv in sorted(new.items()) if kv[1]) or "empty")
        return new

    def _grenades(self, before, after, armed):
        if before is None or after is None or not (armed or self._armed):
            return
        for name, was in before.items():
            if "grenade" in name and was >= 1 and after.get(name, 0) == 0:
                label = backpack.grenade_label(name)
                log.info("Last %s grenade thrown", label)
                self.narrator.say("OnFootLastGrenade", {"grenade": label})

    def _use(self, action, what, words, cooldown, line):
        now = self.clock()
        if what in self._last and now - self._last[what] < cooldown:
            return
        if self._counts is not None and backpack.count_matching(self._counts, *words) <= 0:
            if now - self._last.get(what + "_none", -999) > 30:
                self._last[what + "_none"] = now
                self.narrator.say("OnFootNoSupplies", {"item": "medical packs" if what == "health" else "energy cells"})
            return
        stroke, why = self.book.lookup(action)
        if stroke is None:
            self.last_result = "unbound"
            log.warning("On-foot care: no keyboard key for %s (%s)", action, why)
            self._last[what] = now
            return
        self._last[what] = now
        problem = self.sender.send(stroke)
        self.last_result = problem or "done"
        if problem:
            log.warning("On-foot care could not press the key: %s", problem)
        else:
            log.info("On-foot care: used %s", what)
            self.narrator.say(line, {})
