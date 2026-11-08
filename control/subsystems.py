"""The parts of a scanned ship she can sub target ("sub target the power plant").

The game's journal writes a ShipTargeted line every time you change the selected subsystem, with a name like
"$int_powerplant_size6_class5_name;" and a readable one ("Power Plant"). We match on little pieces of those names.
The exact spelling in the real game has not been checked on a live ship, so every name she sees is written to the log."""

import re

# key -> (what she calls it, pieces of the game's name that mean it)
SUBSYSTEMS = {
    "powerplant": ("the power plant", ("powerplant",)),
    "engines": ("the engines", ("engine", "thruster", "extdrive")),     # the real log calls them "Drive" ($ext_drive_class2_a_name;)
    "fsd": ("the frame shift drive", ("hyperdrive", "frameshift")),
    "shields": ("the shield generator", ("shieldgenerator",)),
    "lifesupport": ("life support", ("lifesupport",)),
    "distributor": ("the power distributor", ("powerdistributor",)),
    "sensors": ("the sensors", ("sensor",)),
    "cargo": ("the cargo hatch", ("modularcargobaydoor", "cargohatch")),   # NOT "cargo": the Manifest Scanner is $hpt_cargoscanner
    "weapons": ("the weapons", ("hpt",)),                            # every weapon is $hpt_... (Beam Laser, Cannon, Pulse Laser ...)
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


# The order the game cycles in (from Benny's 8 Nov 2026 log): the engines ("Drive", twice), power plant, FSD, life support,
# power distributor, shield generator, [FSD interdictor], cargo hatch, then every weapon and the manifest scanner, then round again.
# Used only to choose between Next and Previous Subsystem; she still checks the journal after every press.
RING = ("engines", "powerplant", "fsd", "lifesupport", "distributor", "shields", "cargo", "weapons")


def which(raw, readable=""):
    """The key (see SUBSYSTEMS) of the part the game names, or None when it is not one of the ring parts."""
    for key in RING:
        if matches(key, raw, readable):
            return key
    return None


def shorter_way(current, wanted):
    """'next' or 'previous': whichever is fewer presses round the ring. Unknown current part: 'next'."""
    if current not in RING or wanted not in RING:
        return "next"
    size = len(RING)
    forward = (RING.index(wanted) - RING.index(current)) % size
    backward = (RING.index(current) - RING.index(wanted)) % size
    return "previous" if backward < forward else "next"
