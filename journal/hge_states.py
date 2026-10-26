"""
Which High Grade Emissions materials a system is likely to give, from its controlling faction's allegiance and state.

The table (community-tested; it improves the odds, it never guarantees the material; sources: ED Blackbox, EDMining, newp.io guide,
the Frontier forum guide; "Expansion" counts like "Boom" as the Commander asked):

  Independent / Alliance   Boom or Expansion   Proto Heat Radiators, Proto Light Alloys, Proto Radiolic Alloys
  Empire                   none/Election/Boom/Expansion/Investment   Imperial Shielding
  Federation               none/Election       Core Dynamics Composites, Proprietary Composites
  anyone                   War or Civil War    Military Grade Alloys, Military Supercapacitors
  anyone                   Civil Unrest        Improvised Components (and Military Grade Alloys)
  anyone                   Outbreak            Pharmaceutical Isolators
The war / unrest / outbreak rows win over the allegiance rows.
"""

PROTO = ["Proto Heat Radiators", "Proto Light Alloys", "Proto Radiolic Alloys"]


def _states(faction):
    states = []
    for key in ("FactionState",):
        value = faction.get(key)
        if isinstance(value, str) and value:
            states.append(value)
    for group in ("ActiveStates",):
        for item in faction.get(group) or []:
            value = item.get("State") if isinstance(item, dict) else None
            if isinstance(value, str) and value and value not in states:
                states.append(value)
    return states


def controlling_faction(entry):
    """(allegiance, [states]) of the faction that controls the system, from an FSDJump / Location entry. None when unknown."""
    boss = entry.get("SystemFaction")
    name = boss.get("Name") if isinstance(boss, dict) else None
    found = None
    for faction in entry.get("Factions") or []:
        if isinstance(faction, dict) and (name is None or faction.get("Name") == name):
            found = faction
            break
    states = _states(found) if found else []
    if isinstance(boss, dict):
        for state in _states(boss):
            if state not in states:
                states.append(state)
    allegiance = (found or {}).get("Allegiance") or entry.get("SystemAllegiance")
    if not allegiance and not states and not found:
        return None
    return str(allegiance or "Independent"), states


def likely_materials(entry):
    """(state label, [materials]) for the system in this journal entry, or None when nothing is worth saying."""
    who = controlling_faction(entry)
    if who is None:
        return None
    allegiance, states = who
    low = {s.lower().replace(" ", "") for s in states}
    pretty = {s.lower().replace(" ", ""): s for s in states}

    def label(*names):
        return " and ".join(pretty[n] for n in names if n in pretty)

    if low & {"war", "civilwar"}:
        return label("war", "civilwar"), ["Military Grade Alloys", "Military Supercapacitors"]
    if "outbreak" in low:
        return label("outbreak"), ["Pharmaceutical Isolators"]
    if "civilunrest" in low:
        return label("civilunrest"), ["Improvised Components", "Military Grade Alloys"]
    allegiance = allegiance.lower()
    if allegiance in ("independent", "alliance"):
        if low & {"boom", "expansion"}:
            return label("boom", "expansion"), list(PROTO)
        return None
    if allegiance == "empire":
        if low <= {"boom", "expansion", "investment", "election", "none"}:
            return (label("boom", "expansion", "investment", "election") or "no state"), ["Imperial Shielding"]
        return None
    if allegiance == "federation":
        if low <= {"election", "none"}:
            return (label("election") or "no state"), ["Core Dynamics Composites", "Proprietary Composites"]
        return None
    return None


def spoken_list(materials):
    """['A', 'B', 'C'] -> 'A, B and C'."""
    if len(materials) <= 1:
        return "".join(materials)
    return ", ".join(materials[:-1]) + " and " + materials[-1]
