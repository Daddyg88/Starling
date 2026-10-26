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
    first = data.get("WasDiscovered") is False      # nobody has scanned it before. Out exploring that is common, so only Earth-likes and rare giants get the extra line
    if "earth" in planet:
        return ["Scan_EarthLike_First", "Scan_EarthLike"] if first else ["Scan_EarthLike"]
    if planet == "water world":
        return ["Scan_WaterWorld"]
    if planet == "ammonia world":
        return ["Scan_AmmoniaWorld"]
    if "gas giant with" in planet and "life" in planet:
        return ["Scan_LifeGasGiant"]       # NOT a "green gas giant" (that is a codex entry, see events/codex_entry.py); about 1 in 120 planets in real journals
    if planet in ("water giant", "helium rich gas giant", "sudarsky class v gas giant"):
        return ["Scan_RareGiant_First", "Scan_RareGiant"] if first else ["Scan_RareGiant"]          # about 3 in 10,000 planets in real journals each
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
                "cheer": ["Refined_Cheer"], "total": ["Refined_Total"], "plain": ["Refined_Plain"]}.get(said, [])

    if name == "LaunchDrone":
        return {"prospector": ["Launch_Prospector"], "collection": ["Launch_Collector"]}.get(data.get("Announce"), [])

    if name == "BuyDrones":
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
        if data.get("JumpType") != "Hyperspace":
            return []
        scoop = data.get("Scoopable")
        if scoop is None:
            return ["StartJump"]
        boost = {"neutron": ["StartJump_Neutron"], "whitedwarf": ["StartJump_WhiteDwarf"]}.get(data.get("Boost"), [])
        return boost + ["StartJump_Scoop" if scoop else "StartJump_NoScoop", "StartJump"]

    if name == "ShipyardSwap":
        return (["ShipyardSwap_Favourite"] if data.get("Favourite") else []) + ["ShipyardSwap"]

    if name == "GlideStarted":
        if data.get("temperature") is not None and data.get("gravity") is not None:
            return (["GlideStarted_Heavy"] if data.get("heavy") else []) + ["GlideStarted_Info", "GlideStarted"]
        return ["GlideStarted"]

    if name == "JumpsLeft":
        return ["JumpsLeft_Last"] if data.get("last") else ["JumpsLeft"]

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

    if name == "GreenGasGiant":
        return ["GreenGasGiant_New", "GreenGasGiant"] if data.get("New") else ["GreenGasGiant"]

    if name == "GameMilestone":
        return ["GameMilestone_%s" % data.get("Kind"), "GameMilestone"]
    if name == "UniqueBio":
        return ["UniqueBio"]
    if name == "BioProgress":
        return ["BioProgress_Last"] if data.get("Missing") and data.get("Left") == 1 else (["BioProgress_Missing"] if data.get("Missing") else []) + ["BioProgress"]

    if name == "BioGuess":
        return ["BioGuess_Unknown"] if data.get("Unknown") else ["BioGuess"]
    if name == "BioRefined":
        return ["BioRefined"] if data.get("Right") else ["BioRefined_Wrong"]

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
