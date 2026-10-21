"""
Mining events: prospecting a rock, cracking it, refining a mineral, and launching limpets.
Their words live in voicepacks/default/mining.json. The tiers (what is worth getting excited about) are in mining/minerals.py.
"""

import random
import time

from core.event_bus import NORMAL, LOW
from events.base_event import BaseEvent
from mining import minerals

SESSION_GAP_SECONDS = 3 * 3600
RANK = {"top": 2, "good": 1, "low": 0}
DEPLETED_PERCENT = 1.0        # Remaining (percent of the rock left) at or below this = depleted
NEARLY_GONE_PERCENT = 15.0
GOOD_MIN_PERCENT = 10.0      # a "good" mineral must make up at least this much of the rock to be worth a mention


def _percent_text(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return str(int(round(number)))


class ProspectedAsteroid(BaseEvent):
    """You fired a prospector limpet at a rock: she reads out what is inside."""
    name = "ProspectedAsteroid"
    priority = NORMAL
    summary = "Prospected: {Material} {Percent} percent ({Content})"

    def handle(self, entry):
        content = str(entry.get("Content_Localised") or entry.get("Content") or "")
        low = content.lower()
        level = "High" if "high" in low else ("Medium" if "medium" in low else ("Low" if "low" in low else ""))
        best, best_tier, best_percent = None, "low", 0.0
        for item in entry.get("Materials") or []:
            if not isinstance(item, dict):
                continue
            name = item.get("Name_Localised") or item.get("Name")
            kind = minerals.tier(item.get("Name") or name)
            try:
                percent = float(item.get("Proportion") or 0)
            except (TypeError, ValueError):
                percent = 0.0
            rank, best_rank = RANK[kind], RANK[best_tier]
            if rank > best_rank or (rank == best_rank and percent > best_percent):
                best, best_tier, best_percent = item, kind, percent
        data = {"Content": level or "?", "Material": "", "Percent": "", "Announce": "", "Tier": "low", "Motherlode": False}
        remaining = entry.get("Remaining")
        if "deplet" in low or (isinstance(remaining, (int, float)) and remaining <= DEPLETED_PERCENT):
            data["Announce"] = "depleted"              # she checked the rock again and nothing is left
            return data
        if isinstance(remaining, (int, float)) and remaining <= NEARLY_GONE_PERCENT:
            data["Announce"] = "dry"                   # nearly empty: still prospected, so say so
            return data
        motherlode = entry.get("MotherlodeMaterial_Localised") or entry.get("MotherlodeMaterial")
        if motherlode:
            data["Motherlode"] = True
            data["Material"] = minerals.spoken(entry.get("MotherlodeMaterial"), entry.get("MotherlodeMaterial_Localised"))
            data["Tier"] = minerals.tier(entry.get("MotherlodeMaterial"))
            data["Announce"] = "motherlode"
            return data
        if best is not None and best_tier != "low":
            name = minerals.spoken(best.get("Name"), best.get("Name_Localised"))
            data.update(Material=name, Percent=_percent_text(best_percent), Tier=best_tier)
            if best_tier == "top":
                data["Announce"] = "top"
            elif best_percent >= GOOD_MIN_PERCENT:
                data["Announce"] = "good"
        if not data["Announce"] and level == "Low":
            data["Announce"] = "poor"
        return data


class MiningRefined(BaseEvent):
    """
    A mineral came out of the refinery into your hold (one tonne each time).
    She does NOT call out every tonne (that gets tiring): the first of each good mineral, then every few tonnes,
    now and then a cheer for a top mineral, and a running total. How often is the Mining page's "How chatty" box.
    """
    name = "MiningRefined"
    priority = LOW
    summary = "Refined {Material}"

    # top, good, total, cheer chance, chance of a small remark about an ordinary mineral
    STEPS = {"quiet": (10, 20, 50, 0.0, 0.0), "normal": (5, 10, 25, 0.16, 0.05), "chatty": (3, 5, 10, 0.3, 0.14)}

    def __init__(self):
        self.reset()
        self.rng = random.Random()
        self.clock = time.monotonic

    def reset(self):
        self.counts, self.total, self.last = {}, 0, None

    def handle(self, entry):
        now = self.clock()
        if self.last is not None and now - self.last > SESSION_GAP_SECONDS:
            self.reset()
        self.last = now
        kind = entry.get("Type")
        key = minerals.normal(kind)
        tier = minerals.tier(kind)
        self.counts[key] = self.counts.get(key, 0) + 1
        self.total += 1
        count = self.counts[key]
        top_step, good_step, total_step, chance, plain = self.STEPS.get(minerals.option("chatter", "normal"), self.STEPS["normal"])
        say = ""
        if tier != "low" and count == 1:
            say = "first"
        elif tier == "top" and count % top_step == 0:
            say = "milestone"
        elif tier == "good" and count % good_step == 0:
            say = "milestone"
        elif tier == "top" and chance and self.rng.random() < chance:
            say = "cheer"
        elif tier == "good" and chance and self.rng.random() < chance * 0.6:
            say = "cheer"
        elif total_step and self.total % total_step == 0:
            say = "total"
        elif tier == "low" and plain and self.rng.random() < plain:
            say = "plain"
        return {"Material": minerals.spoken(kind, entry.get("Type_Localised")), "Commodity": key, "Tier": tier,
                "Count": count, "Total": self.total, "Announce": say}


class AsteroidCracked(BaseEvent):
    """A core was cracked open with an explosive charge."""
    name = "AsteroidCracked"
    priority = LOW
    keep = ("Body",)
    summary = "Cracked an asteroid core"


class LaunchDrone(BaseEvent):
    """Limpets launched. She only remarks now and then on prospector and collector limpets (so it never gets tiring)."""
    name = "LaunchDrone"
    priority = LOW
    keep = ("Type",)
    summary = "Launched a {Type} limpet"
    CHANCE = {"prospector": 0.3, "collection": 0.12}

    def __init__(self):
        self.rng = random.Random()

    def handle(self, entry):
        data = super().handle(entry)
        kind = str(entry.get("Type") or "").lower()
        if minerals.option("chatter", "normal") != "quiet" and self.rng.random() < self.CHANCE.get(kind, 0.0):
            data["Announce"] = kind
        return data

