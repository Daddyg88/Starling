"""
Events that come from Status.json: ship controls, screens and vehicles.

Elite Dangerous does not write these into the journal. Instead, Status.json
holds a row of on/off switches ("flags"). STARLING compares them every second
and announces the ones that just changed.

TO ADD ANOTHER SWITCH: add one line to FLAG_ROWS below, then add the new
event names to config/events.json. That is all.

Each row is:
    (status field, bit number,
     name when switched ON,  sentence, priority,
     name when switched OFF, sentence, priority)
Use None for the OFF part if you only care about it switching on.
A sentence of None means the event already has its own file.

The bit numbers come from Frontier's journal documentation.
"""

from core.event_bus import CRITICAL, LOW, NORMAL
from events.base_event import BaseEvent

NONE3 = (None, None, None)

FLAG_ROWS = [
    # ---- ship controls (the "Flags" field) ----
    ("Flags", 2,  "LandingGearDown", "Landing gear down", NORMAL,  "LandingGearUp", "Landing gear up", NORMAL),
    ("Flags", 5,  "FlightAssistOff", "Flight assist off", NORMAL,  "FlightAssistOn", "Flight assist on", NORMAL),
    ("Flags", 6,  "HardpointsDeployed", "Hardpoints deployed", NORMAL,  "HardpointsRetracted", "Hardpoints retracted", NORMAL),
    ("Flags", 7,  "WingJoined", "Joined a wing", NORMAL,  "WingLeft", "Left the wing", NORMAL),
    ("Flags", 8,  "LightsOn", "Lights on", LOW,  "LightsOff", "Lights off", LOW),
    ("Flags", 9,  "CargoScoopDeployed", "Cargo scoop deployed", LOW,  "CargoScoopRetracted", "Cargo scoop retracted", LOW),
    ("Flags", 10, "SilentRunningOn", "Silent running on", NORMAL,  "SilentRunningOff", "Silent running off", NORMAL),
    ("Flags", 11, "FuelScoopStarted", "Fuel scooping started", LOW,  "FuelScoopDisengaged", "Fuel scoop disengaged", NORMAL),
    ("Flags", 17, "FsdCharging", "Frame shift drive charging", NORMAL,  *NONE3),
    ("Flags", 16, "MassLocked", "Frame shift drive is mass locked", NORMAL,  "MassLockReleased", "Mass lock released", NORMAL),
    ("Flags", 18, "FsdCoolingDown", "Frame shift drive cooling down", LOW,  "FsdReady", "Frame shift drive ready", LOW),
    ("Flags", 27, "AnalysisModeOn", "Analysis mode", NORMAL,  "CombatModeOn", "Combat mode", NORMAL),
    ("Flags", 28, "NightVisionOn", "Night vision on", LOW,  "NightVisionOff", "Night vision off", LOW),
    # ---- SRV controls ----
    ("Flags", 12, "SrvHandbrakeOn", "SRV handbrake on", LOW,  "SrvHandbrakeOff", "SRV handbrake off", LOW),
    ("Flags", 13, "SrvTurretViewOn", "SRV turret view", LOW,  "SrvTurretViewOff", "SRV driving view", LOW),
    ("Flags", 14, "SrvTurretRetracted", "SRV turret retracted", LOW,  "SrvTurretDeployed", "SRV turret deployed", LOW),
    ("Flags", 15, "SrvDriveAssistOn", "SRV drive assist on", LOW,  "SrvDriveAssistOff", "SRV drive assist off", LOW),
    ("Flags", 31, "SrvHighBeamOn", "SRV high beam on", LOW,  "SrvHighBeamOff", "SRV high beam off", LOW),
    # ---- safety warnings (always on; see journal/status_reader.py) ----
    ("Flags", 19, "LowFuel", None, CRITICAL,  *NONE3),
    ("Flags", 20, "Overheating", None, CRITICAL,  *NONE3),
    ("Flags", 22, "InDanger", None, CRITICAL,  *NONE3),
    ("Flags", 23, "InterdictionInProgress", "Interdiction in progress", CRITICAL,  *NONE3),
    # ---- on foot (the "Flags2" field) ----
    ("Flags2", 6,  "LowOxygen", "Oxygen is low", CRITICAL,  *NONE3),
    ("Flags2", 7,  "LowHealth", "Health is low", CRITICAL,  *NONE3),
    ("Flags2", 8,  "ColdWarning", "It is getting cold", NORMAL,  *NONE3),
    ("Flags2", 9,  "HotWarning", "It is getting hot", NORMAL,  *NONE3),
    ("Flags2", 10, "VeryColdWarning", "Dangerously cold", CRITICAL,  *NONE3),
    ("Flags2", 11, "VeryHotWarning", "Dangerously hot", CRITICAL,  *NONE3),
    ("Flags2", 12, "GlideStarted", "Gliding", LOW,  "GlideEnded", "Glide finished", LOW),
]

# Which vehicle each switch makes sense in. Vehicles: "main ship", "fighter", "SRV",
# "Nomad" (reported by the game as an SRV), "on foot", "other vehicle". A switch not listed here works anywhere.
# This stops the ship's landing gear flag from being read while you are in the
# SRV, on foot, or in another vehicle like the Nomad.
_SHIP = frozenset({"main ship"})
_SRV = frozenset({"SRV"})
ROW_CONTEXT = {
    "LandingGearDown": frozenset({"main ship", "Nomad"}),
    "FlightAssistOff": frozenset({"main ship", "Nomad"}),
    "HardpointsDeployed": _SHIP,
    "CargoScoopDeployed": _SHIP, "SilentRunningOn": _SHIP, "MassLocked": _SHIP,
    "FsdCoolingDown": _SHIP, "AnalysisModeOn": _SHIP, "FsdCharging": _SHIP,
    "FuelScoopStarted": _SHIP,
    "LightsOn": frozenset({"main ship", "SRV", "Nomad"}),
    "NightVisionOn": frozenset({"main ship", "SRV", "Nomad"}),
    "SrvHandbrakeOn": _SRV, "SrvTurretViewOn": _SRV, "SrvTurretRetracted": _SRV,
    "SrvDriveAssistOn": _SRV, "SrvHighBeamOn": _SRV,
}

# These are ignored while you are in supercruise or jumping, because the game
# flips them automatically around every jump.
SUPPRESS_IN_SUPERCRUISE = frozenset({"HardpointsDeployed"})

# A switch must have been ON this many seconds before its OFF event is announced
# (stops a flicker from announcing "fuel scoop disengaged").
MIN_ON_SECONDS = {"FuelScoopDisengaged": 3.0}

# Names of every bit, used by the debug tool (run_debug.bat).
FLAGS_NAMES = {
    0: "Docked", 1: "Landed", 2: "LandingGearDown", 3: "ShieldsUp", 4: "Supercruise",
    5: "FlightAssistOff", 6: "HardpointsDeployed", 7: "InWing", 8: "LightsOn",
    9: "CargoScoopDeployed", 10: "SilentRunning", 11: "ScoopingFuel", 12: "SrvHandbrake",
    13: "SrvTurretView", 14: "SrvTurretRetracted", 15: "SrvDriveAssist", 16: "FsdMassLocked",
    17: "FsdCharging", 18: "FsdCooldown", 19: "LowFuel", 20: "OverHeating", 21: "HasLatLong",
    22: "IsInDanger", 23: "BeingInterdicted", 24: "InMainShip", 25: "InFighter", 26: "InSRV",
    27: "HudAnalysisMode", 28: "NightVision", 29: "AltitudeFromAverageRadius", 30: "FsdJump",
    31: "SrvHighBeam",
}
FLAGS2_NAMES = {
    0: "OnFoot", 1: "InTaxi", 2: "InMulticrew", 3: "OnFootInStation", 4: "OnFootOnPlanet",
    5: "AimDownSight", 6: "LowOxygen", 7: "LowHealth", 8: "Cold", 9: "Hot", 10: "VeryCold",
    11: "VeryHot", 12: "GlideMode", 13: "OnFootInHangar", 14: "OnFootSocialSpace",
    15: "OnFootExterior", 16: "BreathableAtmosphere", 17: "TelepresenceMulticrew",
    18: "PhysicalMulticrew", 19: "FsdHyperdriveCharging",
}

# The "GuiFocus" field says which screen you are looking at.
SCREENS = {
    1:  ("InternalPanelOpened", "right-hand panel"),
    2:  ("ExternalPanelOpened", "left-hand panel"),
    3:  ("CommsPanelOpened", "comms panel"),
    4:  ("RolePanelOpened", "role panel"),
    5:  ("StationServicesOpened", "station services"),
    6:  ("GalaxyMapOpened", "galaxy map"),
    7:  ("SystemMapOpened", "system map"),
    8:  ("OrreryOpened", "orrery"),
    9:  ("FssOpened", "system scanner"),
    10: ("SaaOpened", "surface scanner"),
    11: ("CodexOpened", "codex"),
}

SCREEN_CLOSED = "ScreenClosed"
VEHICLE_CHANGED = "VehicleChanged"
FUEL_SCOOP_COMPLETE = "FuelScoopComplete"   # worked out from the fuel level, not a switch


def _make(name, summary, priority):
    return type(name, (BaseEvent,), {
        "__module__": __name__,
        "__doc__": "Made from Status.json: " + (summary or name),
        "name": name,
        "priority": priority,
        "source": "status",
        "summary": summary or "",
    })


def _build():
    classes = []
    for _field, _bit, on_name, on_text, on_prio, off_name, off_text, off_prio in FLAG_ROWS:
        if on_text is not None:
            classes.append(_make(on_name, on_text, on_prio))
        if off_name is not None and off_text is not None:
            classes.append(_make(off_name, off_text, off_prio))
    for name, label in SCREENS.values():
        classes.append(_make(name, "Opened the %s" % label, LOW))
    classes.append(_make(SCREEN_CLOSED, "Closed the {screen}", LOW))
    classes.append(_make(VEHICLE_CHANGED, "Now in: {vehicle}", NORMAL))
    classes.append(_make(FUEL_SCOOP_COMPLETE, "Fuel scooping complete: tank full", NORMAL))
    return classes


# The registry looks for this list.
EVENT_CLASSES = _build()
