"""
Mining events: prospecting a rock, cracking it, refining a mineral, and launching limpets.
Their words live in voicepacks/default/mining.json. The tiers (what is worth getting excited about) are in mining/minerals.py.
"""

from core.event_bus import NORMAL, LOW
from events.base_event import BaseEvent
from mining import minerals

RANK = {"top": 2, "good": 1, "low": 0}
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
    """A mineral came out of the refinery into your hold (one tonne each time)."""
    name = "MiningRefined"
    priority = LOW
    summary = "Refined {Material}"

    def handle(self, entry):
        kind = entry.get("Type")
        return {"Material": minerals.spoken(kind, entry.get("Type_Localised")), "Commodity": minerals.normal(kind),
                "Tier": minerals.tier(kind), "Announce": ""}


class AsteroidCracked(BaseEvent):
    """A core was cracked open with an explosive charge."""
    name = "AsteroidCracked"
    priority = LOW
    keep = ("Body",)
    summary = "Cracked an asteroid core"


class LaunchDrone(BaseEvent):
    """Limpets launched. Not spoken; she counts them so she knows you are mining."""
    name = "LaunchDrone"
    priority = LOW
    keep = ("Type",)
    summary = "Launched a {Type} limpet"

