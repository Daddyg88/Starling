"""
She says something when you synthesise: ammo, repairs, FSD boosts, limpets, fuel, heat sinks, chaff.

The journal's Synthesis line carries the recipe name (for example "Restock Basic" or "FSD Premium"). The exact spellings are
not documented, so the recipe is sorted by the words in it, and anything unknown gets a plain line (Synthesis_Generic).
She never talks more than once every 15 seconds, so five ammo syntheses in a row are one line, not five.
"""

import time

from core.logger import get_logger

log = get_logger("synthtalk")

COOLDOWN = 15.0
GRADES = {"basic": "basic", "standard": "standard", "premium": "premium"}
# (words to look for, line group). The first match wins, so the more specific words come first.
KINDS = (
    (("ammo", "restock", "munition", "refill"), "Ammo"),
    (("limpet",), "Limpet"),
    (("fsd", "frame shift", "jump range"), "FSD"),
    (("heat sink", "heatsink"), "Heat"),
    (("chaff",), "Chaff"),
    (("refuel", "fuel"), "Refuel"),
    (("repair", "hull", "armour", "armor"), "Repair"),
)


def kind_of(name):
    """Which group of lines a recipe name belongs to."""
    text = str(name or "").lower()
    for words, kind in KINDS:
        if any(w in text for w in words):
            return kind
    return "Generic"


def grade_of(name):
    text = str(name or "").lower()
    for word, grade in GRADES.items():
        if word in text:
            return grade
    return ""


class SynthesisTalk:
    def __init__(self, bus, settings, narrator, clock=time.monotonic):
        self.bus, self.settings, self.narrator, self.clock = bus, settings, narrator, clock
        self._said_at = None

    def attach(self):
        self.bus.subscribe("Synthesis", self.on_synthesis)

    def detach(self):
        self.bus.unsubscribe("Synthesis", self.on_synthesis)

    def on_synthesis(self, event):
        if not self.settings.get("synthesis.callout", True):
            return
        now = self.clock()
        if self._said_at is not None and now - self._said_at < COOLDOWN:
            return
        name = (getattr(event, "data", None) or {}).get("Name") or ""
        try:
            said = self.narrator.say("Synthesis_" + kind_of(name), {"Grade": grade_of(name), "Recipe": str(name)})
        except Exception:
            log.exception("The synthesis line failed")
            return
        if said is not False:
            self._said_at = now
