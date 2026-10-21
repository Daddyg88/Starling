"""
Works out which dialogue key(s) to use for an event.

Most events simply use their own name ("FuelScoop" looks up "FuelScoop").
The few that need more care are handled here, most specific key first.
"""

# These events share another event's lines.
ALIASES = {
    "FactionKillBond": "Bounty",
    "MultiSellExplorationData": "SellExplorationData",
    "RefuelPartial": "RefuelAll",
    "CapShipBond": "Bounty",
}


def scan_keys(data):
    """
    Ordinary planets and stars are NOT announced (that was annoying).
    Only bodies worth a Commander's attention get a line.
    """
    planet = str(data.get("PlanetClass") or "").lower()
    star = str(data.get("StarType") or "")
    if "earth" in planet:
        return ["Scan_EarthLike"]
    if planet == "water world":
        return ["Scan_WaterWorld"]
    if planet == "ammonia world":
        return ["Scan_AmmoniaWorld"]
    if "gas giant with" in planet and "life" in planet:
        return ["Scan_GreenGasGiant"]      # very rare: it gets its own excited lines
    if data.get("TerraformState") == "Terraformable":
        return ["Scan_Terraformable"]
    if star == "N":
        return ["Scan_NeutronStar"]
    if star in ("H", "SupermassiveBlackHole"):
        return ["Scan_BlackHole"]
    return []


def keys_for(event):
    """The dialogue keys to try, most specific first. On foot, "<Event>_OnFoot" lines come before the ship ones."""
    keys = _keys_for(event)
    if (event.data or {}).get("OnFoot"):
        keys = [ALIASES.get(event.name, event.name) + "_OnFoot"] + keys
    return keys


def _keys_for(event):
    name = event.name
    data = event.data

    if name == "ShipTargeted":
        said = data.get("Announce")
        if said is None:                                  # older style data: only a wanted ship is worth a word
            return ["ShipTargeted_Wanted"] if "wanted" in str(data.get("LegalStatus", "")).lower() else []
        return {"thargoid": ["ShipTargeted_Thargoid"], "ship": ["ShipTargeted_Ship"], "bounty": ["ShipTargeted_Bounty", "ShipTargeted_Wanted"],
                "wanted": ["ShipTargeted_Wanted"]}.get(said, [])

    if name == "ProspectedAsteroid":
        said = data.get("Announce")
        return ["Prospected_" + said.capitalize()] if said else []

    if name == "MiningRefined":
        said, tier = data.get("Announce"), data.get("Tier")
        suffix = "Good" if tier == "good" else ""
        return {"first": ["Refined_First" + suffix], "milestone": ["Refined_Milestone" + suffix],
                "cheer": ["Refined_Cheer"], "total": ["Refined_Total"]}.get(said, [])

    if name in ("LaunchDrone", "BuyDrones"):
        return []

    if name == "Interdiction":
        return ["Interdiction_Success" if data.get("Success") else "Interdiction_Failed"]

    if name == "HullDamage":
        percent = data.get("Percent")
        if isinstance(percent, (int, float)) and percent <= 30:
            return ["HullDamage_Critical", "HullDamage"]
        return ["HullDamage"]

    if name == "ShieldState":
        return ["ShieldsUp"] if data.get("ShieldsUp") else ["ShieldsDown"]

    if name == "DockingDenied":
        reason = data.get("Reason")
        return (["DockingDenied_%s" % reason] if reason else []) + ["DockingDenied"]

    if name == "StartJump":
        # "Four, three, two, one, engage" is for hyperspace jumps only.
        return ["StartJump"] if data.get("JumpType") == "Hyperspace" else []

    if name == "Scan":
        return scan_keys(data)

    if name == "ScreenClosed":
        # Only the two maps are announced; closing any other screen stays quiet.
        return {"galaxy map": ["GalaxyMapClosed"], "system map": ["SystemMapClosed"]}.get(data.get("screen"), [])

    if name == "VehicleChanged":
        vehicle = data.get("vehicle")
        if vehicle == "main ship":
            return ["BoardedShip"]
        if vehicle == "on foot":
            return ["VehicleChanged_OnFoot"]
        return []

    if name in ("SAASignalsFound", "FSSBodySignals"):
        return ["%s_Biological" % name] if data.get("Biological") else [name]

    if name == "ScanOrganic":
        stage = data.get("ScanType")
        if stage == "Analyse":
            if not data.get("ValueKnown"):
                return ["ScanOrganic_AnalyseNoValue", "ScanOrganic_Analyse"]
            return ["ScanOrganic_AnalyseFootfall" if data.get("FirstFootfall") else "ScanOrganic_Analyse"]
        if stage == "Sample" and data.get("SampleNumber") == 3:
            return ["ScanOrganic_Third"]
        if stage == "Sample" and data.get("SampleNumber") == 2 and data.get("About"):
            return ["ScanOrganic_SampleAbout", "ScanOrganic_Sample"]       # the second sample: what it is
        if stage == "Log":
            # the first sample: the value (and excitement about a top-ten species). Four things change the wording.
            tail = "" if data.get("distance") else "NoDistance"
            if not data.get("ValueKnown"):
                core = "LogNoValue"
            else:
                core = "Log" + ("Top10" if data.get("Top10") else "") + ("Footfall" if data.get("FirstFootfall") else "")
            return ["ScanOrganic_%s%s" % (core, tail), "ScanOrganic_Log" + tail]
        return ["ScanOrganic_%s" % stage] if stage else ["ScanOrganic"]

    if name == "SellOrganicData":
        return ["SellOrganicData"] if data.get("TotalValue") else ["SellOrganicData_Plain"]

    return [ALIASES.get(name, name)]
