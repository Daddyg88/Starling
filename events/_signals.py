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
