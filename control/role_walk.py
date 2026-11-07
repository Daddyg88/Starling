"""Walking the ROLE panel (Suit | Launch bay | SRV | Crew) by looking at it. The pieces here know nothing about the game or the
keyboard: `read()` gives what she sees (control.role_reader.read_all), `press(name)` presses UI_Up / UI_Down / UI_Left / UI_Right,
`wait(seconds)` waits. That keeps it easy to test with pictures.

How the role panel works (from the commander's pictures): the four tabs are a VERTICAL list on the left (Up / Down moves between
them); Right moves the cursor into the page, where the lit amber button is the one the cursor is on (Deploy / Disembark); Down /
Up moves between the two rows of a page; Select presses it; Left goes back to the tab list."""
import time

from control import role_reader

TAB_NUMBER = {"suit": 0, "launch": 1, "srv": 2, "crew": 3}
LOOKS = 3                                  # how many times she looks again when she cannot tell yet


def read_all(picture):
    """What she sees in one picture, as a dict (or None if there is no picture)."""
    if picture is None:
        return None
    return {"tab": role_reader.selected_tab(picture), "lit": role_reader.lit_button(picture),
            "grey": role_reader.grey_buttons(picture),
            "rows": (role_reader.row_occupied(picture, 0), role_reader.row_occupied(picture, 1)),
            "text": role_reader.describe(picture)}


def _look(read, wait, need):
    """Looks until `need(seen)` is true, at most LOOKS times (the highlight takes a moment to move). Returns the last look."""
    seen = read()
    for _ in range(LOOKS - 1):
        if seen is None or need(seen):
            break
        wait(0.3)
        seen = read()
    return seen


def go_to_tab(read, press, wait, target, note=None):
    """Gets the role panel onto tab `target` (0 suit, 1 launch bay, 2 SRV, 3 crew). Returns "ok", "unreadable" (no picture / she
    cannot tell which tab is selected) or "failed" (it did not get there)."""
    note = note or (lambda text: None)
    seen = _look(read, wait, lambda s: s["tab"] is not None)
    if seen is None:
        return "unreadable"
    note("first look: %s" % seen["text"])
    if seen["lit"] is not None and seen["tab"] != target:           # a lit button = the cursor may be inside a page: one Left goes back
        press("UI_Left")                                              # to the tab list (if it was already there, Left does nothing)
        wait(0.45)
        seen = _look(read, wait, lambda s: s["tab"] is not None)
        if seen is None:
            return "unreadable"
        note("after Left: %s" % seen["text"])
    for _ in range(5):
        tab = seen["tab"]
        if tab is None:
            return "unreadable"
        if tab == target:
            return "ok"
        for _ in range(abs(target - tab)):
            press("UI_Down" if target > tab else "UI_Up")
            wait(0.3)
        wait(0.2)
        seen = _look(read, wait, lambda s: s["tab"] is not None)
        if seen is None:
            return "unreadable"
        note("after pressing: %s" % seen["text"])
    return "failed"


def pick(read, press, wait, tab, row):
    """On tab `tab`: puts the cursor on `row` (0 top, 1 second, None = wherever the game puts it) and presses Select on the lit button.
    Returns ("ok", None) after Select, ("missing", None) if that row has no vessel, ("blocked", None) if the button is not available
    (grey, or the cursor would not go there), ("unreadable", None) if she cannot see enough to act."""
    seen = _look(read, wait, lambda s: s["tab"] is not None or s["lit"] is not None)
    if seen is None:
        return "unreadable", None
    if tab in (1, 2) and row is not None and seen["rows"][row] is False:
        return "missing", None                                        # nothing in that slot
    if seen["lit"] is None:
        press("UI_Right")                                             # into the page
        wait(0.55)
        seen = _look(read, wait, lambda s: s["lit"] is not None)
        if seen is None:
            return "unreadable", None
    if seen["lit"] is None:
        return ("blocked", None) if seen["grey"] else ("unreadable", None)
    if tab in (1, 2) and row is not None:
        if seen["rows"][row] is False:
            return "missing", None
        for _ in range(2):
            lit_row = seen["lit"]["row"]
            if lit_row == row:
                break
            press("UI_Down" if row > lit_row else "UI_Up")
            wait(0.45)
            seen = _look(read, wait, lambda s: s["lit"] is not None and s["lit"]["row"] == row)
            if seen is None:
                return "unreadable", None
            if seen["lit"] is None:
                return "blocked", None                                # the wanted button went grey / the cursor left
        if seen["lit"] is None or seen["lit"]["row"] != row:
            return "blocked", None                                    # the cursor would not go to that row: it is not available
    press("UI_Select")
    return "ok", None


def blocked_reason(kind, flags, altitude):
    """Why she thinks the button is greyed out, from Status.json (flags: the Flags number, altitude in metres or None).
    'landed' = needs landing, 'high30' = the Rhino needs 30 m or lower, 'slf_low' = the fighter needs 500 m or higher,
    'other' = she cannot tell."""
    landed = bool(flags & 2)
    if kind == "slf":
        return "slf_low" if altitude is not None and altitude < 500 else "other"
    if kind == "rhino":
        if landed:
            return "other"
        return "high30" if altitude is not None and altitude > 30 else "landed"
    if kind in ("scarab", "srv", "disembark"):
        return "other" if landed else "landed"
    return "other"
