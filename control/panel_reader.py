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
WAIT_AFTER_KEY = 0.7         # seconds the panel takes to change tab before she looks again


def capture_screen():
    """The whole desktop as a numpy RGB picture (Windows). None if it cannot be taken (not Windows, or a black frame)."""
    try:
        import numpy as np
        from PIL import ImageGrab
        picture = np.asarray(ImageGrab.grab(all_screens=True).convert("RGB"))
    except Exception:
        log.debug("Screen capture is not available", exc_info=True)
        return None
    if picture.size == 0 or picture.max() < 30:               # a fully black frame: the game is not capturable (exclusive fullscreen)
        return None
    return picture


def find_tab(picture):
    """The selected tab bar in a picture: {"cx", "width", "y"} as fractions of the picture, or None."""
    import numpy as np
    if picture is None or picture.ndim != 3:
        return None
    height, width = picture.shape[:2]
    step = max(1, width // SMALL_WIDTH)
    small = picture[::step, ::step].astype(np.int16)
    peak, low = small.max(axis=2), small.min(axis=2)
    mask = (peak >= MIN_BRIGHT) & ((peak - low) >= MIN_SATURATION * np.maximum(peak, 1))
    rows, cols = mask.shape
    seen = np.zeros_like(mask)
    best = None
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
            box_w, box_h = x1 - x0 + 1, y1 - y0 + 1
            if count < MIN_AREA or box_w < MIN_ASPECT * box_h or count < 0.5 * box_w * box_h:
                continue                                       # too small, not a wide bar, or not a solid fill
            if best is None or y0 < best[0]:                   # the top-most one is the tab bar (the rows of a list are lower down)
                best = (y0, x0, x1)
    if best is None:
        return None
    y0, x0, x1 = best
    return {"cx": (x0 + x1 + 1) / 2.0 / cols, "width": (x1 - x0 + 1) / float(cols), "y": y0 / float(rows)}


def goto_tab(read, press_next, press_previous, wait, target):
    """Walk to tab number `target` (0 = Navigation, 1 = Transactions, 2 = Contacts) by looking after every key.

    read()           -> what find_tab gives for the screen right now, or None
    press_next()     press the 'next panel tab' key;  press_previous() the 'previous' one
    wait(seconds)    pause
    Returns True when she got there and could see that she did, False when she could not tell (the caller then falls back to
    counting presses blind, the way the macro always did)."""
    here = read()
    if here is None:
        return False
    for _ in range(5):                                         # step 1: to the first tab (previous either stays put or wraps round)
        press_previous()
        wait(WAIT_AFTER_KEY)
        now = read()
        if now is None:
            return False
        moved = (now["cx"] - here["cx"]) / max(here["width"], 0.01)
        if moved < -0.5:                                       # went one tab to the left: keep going
            here = now
            continue
        if moved > 1.2:                                        # jumped to the far right: it wrapped, so it WAS on the first tab
            press_next()
            wait(WAIT_AFTER_KEY)
            back = read()
            if back is None:
                return False
            here = back
            break
        here = now                                             # did not move: this is the first tab
        break
    else:
        return False                                           # still moving after five presses: something is odd
    for _ in range(target):                                    # step 2: forward to the one we want, checking each press worked
        press_next()
        wait(WAIT_AFTER_KEY)
        now = read()
        if now is None or (now["cx"] - here["cx"]) / max(here["width"], 0.01) < 0.5:
            return False
        here = now
    return True
