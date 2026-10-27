"""
You flew through a neutron or white dwarf jet cone.

The event is always published (the neutron route follower needs every boost), but she only speaks sometimes: on the
first boost of a run, on round numbers (10, 25, 50, 75, 100 and every 25 after) and then now and again. A run ends
when 30 minutes pass without a boost. Her words are in voicepacks/default/variety.json.
"""

import random
import time

from events.base_event import BaseEvent
from core.event_bus import NORMAL

RUN_GAP_SECONDS = 30 * 60
SPEAK_CHANCE = 0.2
MILESTONES = (10, 25, 50, 75, 100)


def is_milestone(count):
    return count in MILESTONES or (count > 100 and count % 25 == 0)


class JetConeBoost(BaseEvent):
    name = "JetConeBoost"
    priority = NORMAL
    keep = ("BoostValue",)
    summary = "Jet cone boost x{BoostValue:.1f}"

    def __init__(self):
        self.count = 0
        self._last = None

    def update_state(self, entry, state):
        now = time.time()
        run = getattr(state, "jet_boosts", 0)
        last = getattr(state, "jet_boost_time", None)
        if last is None or now - last > RUN_GAP_SECONDS:
            run = 0                                   # a new run of cones
        state.jet_boosts = run + 1
        state.jet_boost_time = now
        self.count = state.jet_boosts

    def handle(self, entry):
        data = super().handle(entry)
        count = self.count or 1
        data["Count"] = count
        if count == 1:
            data["Announce"] = "first"
        elif is_milestone(count):
            data["Announce"] = "milestone"
        elif random.random() < SPEAK_CHANCE:
            data["Announce"] = "plain"
        else:
            data["Announce"] = ""
        return data
