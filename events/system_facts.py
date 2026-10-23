"""What the journal says about the system you are in (FSDJump and Location both carry it). Used by the Home page."""


def remember_system_facts(entry, state):
    security = entry.get("SystemSecurity_Localised") or entry.get("SystemSecurity")
    if isinstance(security, str) and security:
        state.system_security = security.replace("$SYSTEM_SECURITY_", "").replace(";", "").strip().capitalize() + " Security" \
            if security.startswith("$") else security
    allegiance = entry.get("SystemAllegiance")
    state.system_allegiance = allegiance if isinstance(allegiance, str) and allegiance else (
        "Independent" if "SystemAllegiance" in entry else state.system_allegiance)
    population = entry.get("Population")
    if isinstance(population, (int, float)):
        state.system_population = int(population)


def remember_star_pos(entry, state):
    """The galaxy coordinates of the system (journal "StarPos": [x, y, z]). The emergency route finder needs them."""
    pos = entry.get("StarPos")
    if isinstance(pos, (list, tuple)) and len(pos) == 3 and all(isinstance(v, (int, float)) for v in pos):
        state.star_pos = (float(pos[0]), float(pos[1]), float(pos[2]))
