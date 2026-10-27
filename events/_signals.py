"""Shared helper: counts the kinds of signals on a planet (biological, geological...)."""


def count_signals(signals):
    counts = {"Biological": 0, "Geological": 0, "Human": 0, "Guardian": 0, "Thargoid": 0, "Other": 0}
    for item in signals or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("Type_Localised") or item.get("Type") or "").lower()
        amount = item.get("Count", 1)
        amount = amount if isinstance(amount, int) else 1
        for name in ("Biological", "Geological", "Human", "Guardian", "Thargoid"):
            if name.lower() in label:
                counts[name] += amount
                break
        else:
            counts["Other"] += amount
    return counts


def describe_counts(body, counts):
    parts = ["%d %s" % (n, name.lower()) for name, n in counts.items() if n]
    return "Signals on %s: %s" % (body or "this body", ", ".join(parts) or "none")


# ---------------------------------------------------------------- ring hotspots
_WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]
_NOT_MINERALS = ("biological", "geological", "human", "guardian", "thargoid", "saa_signaltype", "$")


def is_ring(name):
    """'Synuefe AB-C d1 3 A Ring' -> True. Only rings have hotspots."""
    return str(name or "").strip().lower().endswith(" ring")


def ring_hotspots(entry):
    """[('Platinum', 2), ('Painite', 1)] for a ring that has been mapped, biggest first. Empty for anything that is not a ring."""
    if not is_ring(entry.get("BodyName")):
        return []
    found = {}
    for item in entry.get("Signals") or []:
        if not isinstance(item, dict):
            continue
        raw = str(item.get("Type") or "")
        label = str(item.get("Type_Localised") or raw).strip()
        if not label or any(skip in (raw + " " + label).lower() for skip in _NOT_MINERALS):
            continue
        amount = item.get("Count", 1)
        found[label] = found.get(label, 0) + (amount if isinstance(amount, int) and amount > 0 else 1)
    return sorted(found.items(), key=lambda pair: (-pair[1], pair[0]))


def _number(n):
    return _WORDS[n] if 0 <= n < len(_WORDS) else str(n)


def ring_data(entry, favourites=None):
    """What she says about a mapped ring: {Hotspots, Total, Word, Summary, Favourite} or {} when it has no hotspots.
    Summary reads 'two platinum, one painite and one monazite'; Favourite names the first mineral you chose as a favourite."""
    spots = ring_hotspots(entry)
    if not spots:
        return {}
    total = sum(count for _, count in spots)
    pieces = ["%s %s" % (_number(count), name.lower()) for name, count in spots]
    summary = pieces[0] if len(pieces) == 1 else ", ".join(pieces[:-1]) + " and " + pieces[-1]
    favourite = ""
    if favourites:
        from mining.minerals import normal
        favourite = next((name for name, _ in spots if normal(name) in favourites), "")
    return {"Hotspots": [{"Mineral": n, "Count": c} for n, c in spots], "Total": _number(total), "Word": "hotspot" if total == 1 else "hotspots",
            "Summary": summary, "Favourite": favourite}


def ring_once(entry, state):
    """(ring data, repeat). repeat is True when she has already told you about this ring (the game can say it twice)."""
    try:
        from mining import minerals
        favourites = minerals.favourites()
    except Exception:
        favourites = set()
    data = ring_data(entry, favourites)
    if not data:
        return {}, False
    told = state.__dict__.setdefault("rings_told", set())
    key = (entry.get("BodyName"), data["Summary"])
    repeat = key in told
    told.add(key)
    return data, repeat
