"""The parts of a scanned ship she can sub target ("sub target the power plant").

The game's journal writes a ShipTargeted line every time you change the selected subsystem, with a name like
"$int_powerplant_size6_class5_name;" and a readable one ("Power Plant"). We match on little pieces of those names.
The exact spelling in the real game has not been checked on a live ship, so every name she sees is written to the log."""

import re

# key -> (what she calls it, pieces of the game's name that mean it)
SUBSYSTEMS = {
    "powerplant": ("the power plant", ("powerplant",)),
    "engines": ("the engines", ("engine", "thruster")),
    "fsd": ("the frame shift drive", ("hyperdrive", "frameshift")),
    "shields": ("the shield generator", ("shieldgenerator",)),
    "lifesupport": ("life support", ("lifesupport",)),
    "distributor": ("the power distributor", ("powerdistributor",)),
    "sensors": ("the sensors", ("sensor",)),
    "cargo": ("the cargo hatch", ("cargo",)),
}


def squash(*names):
    """'$int_PowerPlant_size6;' + 'Power Plant' -> 'intpowerplantsize6powerplant' (letters and digits only, lower case)."""
    return re.sub(r"[^a-z0-9]", "", " ".join(str(n or "") for n in names).lower())


def matches(key, raw, readable=""):
    """True when the subsystem the game names (raw, readable) is the one called `key`."""
    if key not in SUBSYSTEMS:
        return False
    text = squash(raw, readable)
    return any(piece in text for piece in SUBSYSTEMS[key][1])
