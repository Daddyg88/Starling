"""
Macros: a list of steps she carries out one after another, for things Elite has no single key for
(requesting docking, deploying the Nomad).

A step is one of:
    "FocusLeftPanel"       press whatever key you have bound to that Elite action
    "UI_Down x3"           press it three times
    "wait 0.5"             pause for half a second
    "hold UI_Select 1.5"   hold that key down for 1.5 seconds (longest 5)
    "paste"                press Ctrl+V (pastes what is on the clipboard, e.g. the next neutron waypoint)
    "enter"                press the Enter key
"""

import re

MAX_STEPS = 60
MAX_WAIT = 5.0
MAX_REPEAT = 12
LITERALS = ("paste", "enter")   # keys that are not in your Elite controls: Ctrl+V and Enter
GAP_SECONDS = 0.12            # a short pause between key presses so the game keeps up

_STEP = re.compile(r"^\s*([A-Za-z0-9_]+)\s*(?:[x*]\s*(\d+))?\s*$")


def parse_macro(steps):
    """[("wait", s) | ("press", action, count) | ("hold", action, s) | ("literal", "paste"|"enter")] - raises ValueError for a step that makes no sense."""
    parsed = []
    for raw in steps or ():
        text = str(raw).strip()
        if not text:
            continue
        if text.lower().startswith("wait"):
            try:
                seconds = float(text[4:].strip() or "0.5")
            except ValueError:
                raise ValueError("I don't understand this wait: %r" % text)
            parsed.append(("wait", max(0.0, min(seconds, MAX_WAIT))))
            continue
        lowered = text.lower()
        if lowered in LITERALS:
            parsed.append(("literal", lowered))
            continue
        if lowered == "hold" or lowered.startswith("hold "):
            bits = text.split()
            try:
                if len(bits) != 3 or not re.match(r"^[A-Za-z0-9_]+$", bits[1]):
                    raise ValueError
                seconds = float(bits[2])
            except ValueError:
                raise ValueError("I don't understand this hold (write it like: hold UI_Select 1.5): %r" % text)
            parsed.append(("hold", bits[1], max(0.1, min(seconds, MAX_WAIT))))
            continue
        match = _STEP.match(text)
        if not match:
            raise ValueError("I don't understand this step: %r" % text)
        parsed.append(("press", match.group(1), max(1, min(int(match.group(2) or 1), MAX_REPEAT))))
    if len(parsed) > MAX_STEPS:
        raise ValueError("That macro has too many steps (limit %d)." % MAX_STEPS)
    return parsed


def actions_in(parsed):
    seen = []
    for step in parsed:
        if step[0] in ("press", "hold") and step[1] not in seen:
            seen.append(step[1])
    return seen
