"""Lets her LOOK at the left-hand panel (Navigation | Transactions | Contacts | Target) so a macro can be sure which tab is open.

Why: the game opens the panel on whichever tab you used last. The docking macro used to press 'next tab' twice and hope it started
on Navigation. Now she looks first.

How (no reading of words, no internet, nothing saved): she takes one screenshot in memory, finds the bright filled bar that is
the selected tab (it is the top-most wide, short, bright block on the screen) and measures where it is. Pressing next/previous
tab and looking again tells her which way and how far it moved, so she can walk to the first tab (it either stays put or wraps
round) and then count forward. The screenshot is thrown away straight away.

The pure parts (find_tab, goto_tab) are tested with made-up pictures and a pretend game; capture_screen only works on Windows."""
from core.logger import get_logger

log = get_logger("panel")

SMALL_WIDTH = 480            # the picture is shrunk to about this wide before looking: quick and still sharp enough
MIN_BRIGHT = 190             # a selected-tab pixel is bright...
MIN_SATURATION = 0.75        # ...and strongly coloured (any HUD colour: orange, blue, green...)
MIN_AREA = 40                # in shrunk pixels
MIN_ASPECT = 3.0             # the tab bar is much wider than it is tall
TAB_MIN_WIDTH = 0.08         # a selected tab is this wide, as a fraction of the screen width (about 0.12 to 0.14 in practice)
TAB_MAX_WIDTH = 0.19
ICON_MIN = 0.012            # the small square icon tab is this wide, as a fraction of the screen width
ICON_MAX = 0.04
WAIT_AFTER_KEY = 0.5         # seconds the panel takes to change tab before she looks again


_announced = []


def game_box():
    """(left, top, right, bottom) of the window in front (Elite, when she presses keys), or None. Windows only.
    Needed because on a multi-monitor desktop the whole desktop can be 5760 pixels wide: shrunk to look at, the tab bar
    became a 3-pixel smudge and she could not see it."""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        try:
            user32.SetProcessDPIAware()                          # real pixels, not scaled ones
        except Exception:
            pass
        window = user32.GetForegroundWindow()
        rect = wintypes.RECT()
        if not window or not user32.GetWindowRect(window, ctypes.byref(rect)):
            return None
        box = (rect.left, rect.top, rect.right, rect.bottom)
        if box[2] - box[0] < 800 or box[3] - box[1] < 450:       # not a game-sized window
            return None
        return box
    except Exception:
        return None


def capture_screen():
    """The game window (or, if that cannot be found, the main screen) as a numpy RGB picture (Windows). None if it cannot be
    taken (not Windows, or a black frame)."""
    try:
        import numpy as np
        from PIL import ImageGrab
        box = game_box()
        if box is not None:
            picture = np.asarray(ImageGrab.grab(bbox=box, all_screens=True).convert("RGB"))
        else:
            picture = np.asarray(ImageGrab.grab().convert("RGB"))
    except Exception:
        log.debug("Screen capture is not available", exc_info=True)
        return None
    if not _announced:
        _announced.append(True)
        log.info("Panel: looking at %dx%d pixels (%s).", picture.shape[1], picture.shape[0],
                 "the game window at %s" % (box,) if box else "the main screen: the game window was not found")
    if picture.size == 0 or picture.max() < 30:               # a fully black frame: the game is not capturable (exclusive fullscreen)
        return None
    return picture


def _blobs(picture):
    """Every bright, strongly coloured, solid blob in the picture as (x0, x1, y0, y1, area) in shrunk-picture pixels, plus the
    shrunk size (columns, rows). Only numpy: a flood fill on a picture about 480 pixels wide."""
    import numpy as np
    height, width = picture.shape[:2]
    step = max(1, width // SMALL_WIDTH)
    small = picture[::step, ::step].astype(np.int16)
    peak, low = small.max(axis=2), small.min(axis=2)
    mask = (peak >= MIN_BRIGHT) & ((peak - low) >= MIN_SATURATION * np.maximum(peak, 1))
    rows, cols = mask.shape
    seen = np.zeros_like(mask)
    blobs = []
    for y in range(rows):
        for x in range(cols):
            if not mask[y, x] or seen[y, x]:
                continue
            stack, count = [(y, x)], 0
            seen[y, x] = True
            x0 = x1 = x
            y0 = y1 = y
            while stack:
                cy, cx = stack.pop()
                count += 1
                x0, x1, y0, y1 = min(x0, cx), max(x1, cx), min(y0, cy), max(y1, cy)
                for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                    if 0 <= ny < rows and 0 <= nx < cols and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if count >= MIN_AREA:
                blobs.append((x0, x1, y0, y1, count))
    return blobs, cols, rows


def _wide_bars(picture):
    """The solid wide, short blobs (tab bars, buttons) as dicts of fractions of the picture, top to bottom."""
    if picture is None or picture.ndim != 3:
        return [], []
    blobs, cols, rows = _blobs(picture)
    bars = []
    for x0, x1, y0, y1, count in blobs:
        box_w, box_h = x1 - x0 + 1, y1 - y0 + 1
        if box_w >= MIN_ASPECT * box_h and count >= 0.5 * box_w * box_h:
            bars.append({"cx": (x0 + x1 + 1) / 2.0 / cols, "width": box_w / float(cols), "y": y0 / float(rows),
                         "height": box_h / float(rows), "x0": x0 / float(cols)})
    bars.sort(key=lambda bar: bar["y"])
    return bars, blobs


def find_tab(picture):
    """The selected tab in a picture: {"cx", "width", "y"} (fractions of the picture), or None.
    Normally that is the top-most wide bright bar. The panel also has a small square icon tab on the far LEFT (one step left of
    Navigation, the Previous Tab key lands on it): when that is the selected one there is no wide bar, so she reports
    {"icon": True, ...} instead."""
    bars, blobs = _wide_bars(picture)
    bars = [bar for bar in bars if TAB_MIN_WIDTH <= bar["width"] <= TAB_MAX_WIDTH]   # a tab is about 0.12-0.14 of the screen wide: not a row or a long bar
    if bars:
        top = bars[0]
        return {"cx": top["cx"], "width": top["width"], "y": top["y"]}
    if picture is None or picture.ndim != 3 or not blobs:
        return None
    _, cols, rows = _blobs_shape(picture)
    for x0, x1, y0, y1, count in sorted(blobs, key=lambda blob: blob[2]):
        box_w, box_h = x1 - x0 + 1, y1 - y0 + 1
        if (0.6 <= box_w / float(box_h) <= 1.8 and ICON_MIN <= box_w / float(cols) <= ICON_MAX
                and x0 / float(cols) < 0.4 and count >= 0.5 * box_w * box_h):
            return {"icon": True, "cx": (x0 + x1 + 1) / 2.0 / cols, "width": box_w / float(cols), "y": y0 / float(rows)}
    return None


def _blobs_shape(picture):
    height, width = picture.shape[:2]
    step = max(1, width // SMALL_WIDTH)
    return None, len(range(0, width, step)), len(range(0, height, step))


def find_button(picture):
    """The big bright bar of the selected button in the right-hand pane (the 'Request Docking' button) when the cursor is on
    it, or None. It must be well below the tab bar and in the right part of the panel."""
    bars, _ = _wide_bars(picture)
    tab = find_tab(picture)
    if not bars or tab is None:
        return None
    for bar in bars:
        if bar["y"] > tab["y"] + 0.12 and bar["cx"] > tab["cx"] - 0.1 and 0.05 <= bar["width"] <= 0.35 and bar["x0"] > 0.3:
            return bar
    return None


def describe(spot):
    """A short text for the log: what she saw."""
    if spot is None:
        return "nothing"
    return "%s(x=%.3f, w=%.3f, y=%.3f)" % ("icon" if spot.get("icon") else "tab", spot["cx"], spot["width"], spot["y"])


def find_list_row(picture):
    """The lit row in the contact LIST on the left (the cursor is in the list, not on a button), or None."""
    bars, _ = _wide_bars(picture)
    tab = find_tab(picture)
    if not bars or tab is None:
        return None
    for bar in bars:
        if bar["y"] > tab["y"] + 0.05 and bar["cx"] < tab["cx"] - 0.1 and 0.15 <= bar["width"] <= 0.5:
            return bar
    return None


def describe_button(bar):
    """A short text for the log: where the selected button was (fractions of the window)."""
    if bar is None:
        return "no selected button seen"
    return "button seen (x=%.3f..%.3f, y=%.3f, w=%.3f, h=%.3f)" % (bar["x0"], bar["x0"] + bar["width"], bar["y"], bar["width"], bar["height"])


def mask_png(picture, path):
    """Saves ONLY the black-and-white 'what is bright' map (about 480 pixels wide, no game picture) so a failed look can be
    studied afterwards without keeping a screenshot. Returns True if it was written."""
    try:
        import numpy as np
        from PIL import Image
        step = max(1, picture.shape[1] // SMALL_WIDTH)
        small = picture[::step, ::step].astype(np.int16)
        peak, low = small.max(axis=2), small.min(axis=2)
        mask = (peak >= MIN_BRIGHT) & ((peak - low) >= MIN_SATURATION * np.maximum(peak, 1))
        Image.fromarray((mask * 255).astype(np.uint8)).save(str(path))
        return True
    except Exception:
        return False


def goto_tab(read, press_next, press_previous, wait, target, note=None, memory=None):
    """Walk to tab number `target` (0 = Navigation, 1 = Transactions, 2 = Contacts) by looking after every key.

    read()           -> what find_tab gives for the screen right now, or None
    press_next()     press the 'next panel tab' key;  press_previous() the 'previous' one
    wait(seconds)    pause
    note(text)       (optional) is told what happens at every step, for the log
    memory           (optional) a dict she keeps between walks: where each tab was last seen (index 0 = the icon tab, 1 = Navigation,
                     2 = Transactions, 3 = Contacts, as a fraction of the window width). With it, a later walk recognises which
                     tab it starts on by position and presses the exact number of keys, instead of walking to the first tab
                     and counting from there (about 4 seconds faster). If anything looks different she walks the long way.
    Returns True when she got there and could see that she did, False when she could not tell (the caller then falls back to
    counting presses blind, the way the macro always did)."""
    say = note or (lambda text: None)
    goal = target + 1                                          # index: 0 = icon tab, 1 = Navigation, 2 = Transactions, 3 = Contacts

    def remember(index, spot):
        if memory is not None and spot is not None:
            memory[index] = spot["cx"]

    def look(after):
        """Look once the panel has settled: two looks 0.2 s apart must agree (the tab highlight slides for a moment)."""
        first = read()
        for _ in range(3):
            wait(0.2)
            second = read()
            if first is not None and second is not None and abs(first["cx"] - second["cx"]) < 0.01 \
                    and bool(first.get("icon")) == bool(second.get("icon")):
                say("%s -> %s" % (after, describe(second)))
                return second
            first = second
        say("%s -> %s (never settled)" % (after, describe(first)))
        return first

    here = look("start")
    if here is None:
        return False

    # Shortcut: she knows which tab this is (the icon, or a position she has seen before): press exactly the keys needed.
    index = None
    if here.get("icon"):
        index = 0
    elif memory:
        near = [(abs(here["cx"] - cx), k) for k, cx in memory.items() if k > 0]
        if near and min(near)[0] < 0.4 * max(here["width"], 0.05):
            index = min(near)[1]
    if index is not None:
        remember(index, here)
        while index != goal:
            step = 1 if goal > index else -1
            (press_next if step > 0 else press_previous)()
            wait(WAIT_AFTER_KEY)
            now = look("next" if step > 0 else "previous")
            if now is None:
                return False
            moved = (now["cx"] - here["cx"]) / max(here["width"], 0.01)
            if (step > 0 and moved < 0.5) or (step < 0 and moved > -0.5):
                say("it did not move the way she expected: walking the long way")
                here, index = now, None
                break
            index += step
            here = now
            remember(index, here)
        if index == goal:
            return True

    if not here.get("icon"):
        for _ in range(6):                                     # step 1: left until she is on the little icon tab (the very first one)
            press_previous()
            wait(WAIT_AFTER_KEY)
            now = look("previous")
            if now is None:
                return False
            if now.get("icon"):
                here = now
                break
            moved = (now["cx"] - here["cx"]) / max(here["width"], 0.01)
            if moved < -0.5:                                   # went one tab to the left: keep going
                here = now
                continue
            if moved > 1.2:                                    # jumped to the far right: it wrapped (no icon tab on this panel)
                press_next()
                wait(WAIT_AFTER_KEY)
                back = look("next (it had wrapped)")
                if back is None:
                    return False
                here = back
                break
            here = now                                         # did not move: this is the first tab
            break
        else:
            return False                                       # still moving after six presses: something is odd
    position = 1
    if here.get("icon"):                                       # one step right of the icon is Navigation (tab 0)
        remember(0, here)
        press_next()
        wait(WAIT_AFTER_KEY)
        now = look("next from the icon")
        if now is None or now.get("icon"):
            return False
        here = now
    remember(position, here)
    for _ in range(target):                                    # step 2: forward to the one we want, checking each press worked
        press_next()
        wait(WAIT_AFTER_KEY)
        now = look("next")
        if now is None or (now["cx"] - here["cx"]) / max(here["width"], 0.01) < 0.5:
            return False
        here = now
        position += 1
        remember(position, here)
    return True
