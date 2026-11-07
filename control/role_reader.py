"""Reads the ROLE panel (the bottom panel: Suit | Launch bay | SRV | Crew) from a screenshot. Only numpy.

What she can see there:
  * which of the four vertical tabs is the selected one (it is filled a little brighter than the others),
  * the lit amber button (the cursor is on it: Deploy / Disembark), as top row (0) or second row (1),
  * a grey button ("CANNOT DEPLOY"),
  * whether a row has a vessel in it at all (the orange wireframe picture on its left).
Positions are measured from the centre of the window in units of the window HEIGHT, because the cockpit is drawn by height:
the same numbers work on 1080p, 1440p, 4K and ultrawide."""
TABS = ("suit", "launch", "srv", "crew")
TAB_X = -0.403                       # centre of the tab column, in window heights from the centre
TAB_HALF_W = 0.030
TAB_Y = (0.370, 0.451, 0.535, 0.620)  # centre of each tab, as a fraction of the window height
TAB_HALF_H = 0.028
TAB_MARGIN = 18                      # the selected tab must be this much brighter (red channel median) than the rest
ROW_ART_X = (-0.343, -0.102)
ROW_ART_Y = ((0.385, 0.545), (0.575, 0.745))
ROW_ART_MIN = 60                     # orange wireframe pixels (sampled every 4th pixel) needed to call a row "occupied" (an unselected row's lines are dim)
SMALL_WIDTH = 480
MIN_AREA = 30


def _small(picture):
    step = max(1, picture.shape[1] // SMALL_WIDTH)
    return picture[::step, ::step].astype("int16"), step


def _flood(mask):
    """Blobs of a True/False picture as (x0, x1, y0, y1, count)."""
    import numpy as np
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
    return blobs


def _row_of(y_fraction):
    return 0 if y_fraction < 0.6 else 1


def _bars(picture, mask_function, min_width):
    """Wide solid bars in a mask: dicts of fractions of the window, top to bottom."""
    if picture is None or getattr(picture, "ndim", 0) != 3:
        return []
    small, _ = _small(picture)
    rows, cols = small.shape[:2]
    bars = []
    for x0, x1, y0, y1, count in _flood(mask_function(small)):
        box_w, box_h = x1 - x0 + 1, y1 - y0 + 1
        width = box_w / float(cols)
        if box_w >= 2.5 * box_h and count >= 0.45 * box_w * box_h and min_width <= width <= 0.3:
            centre_y = (y0 + y1 + 1) / 2.0 / rows
            bars.append({"cx": (x0 + x1 + 1) / 2.0 / cols, "y": centre_y, "width": width,
                         "height": box_h / float(rows), "row": _row_of(centre_y)})
    bars.sort(key=lambda bar: bar["y"])
    return bars


def _amber(small):
    red, green, blue = small[..., 0], small[..., 1], small[..., 2]
    return (red >= 185) & (green >= 105) & (green <= 170) & (blue <= 45)


def _grey(small):
    red, green, blue = small[..., 0], small[..., 1], small[..., 2]
    return (abs(red - green) <= 6) & (abs(green - blue) <= 6) & (red >= 20) & (red <= 80)


def lit_button(picture):
    """The lit (cursor-on) amber button of the role panel: {"cx","y","width","height","row"} or None. Only buttons below the title."""
    for bar in _bars(picture, _amber, 0.08):
        if 0.42 <= bar["y"] <= 0.78:
            return bar
    return None


def grey_buttons(picture):
    """The grey 'CANNOT DEPLOY' buttons, top to bottom."""
    return [bar for bar in _bars(picture, _grey, 0.08) if 0.42 <= bar["y"] <= 0.78 and abs(bar["cx"] - 0.5) < 0.2]


def selected_tab(picture):
    """0 suit, 1 launch bay, 2 SRV, 3 crew: the tab that is filled brighter than the rest, or None if she cannot tell."""
    if picture is None or getattr(picture, "ndim", 0) != 3:
        return None
    import numpy as np
    height, width = picture.shape[:2]
    values = []
    for centre in TAB_Y:
        x0 = int(width / 2.0 + (TAB_X - TAB_HALF_W) * height)
        x1 = int(width / 2.0 + (TAB_X + TAB_HALF_W) * height)
        y0, y1 = int((centre - TAB_HALF_H) * height), int((centre + TAB_HALF_H) * height)
        cell = picture[max(0, y0):y1, max(0, x0):x1, 0]
        if cell.size == 0:
            return None
        values.append(float(np.median(cell)))
    best = max(range(4), key=lambda index: values[index])
    others = max(value for index, value in enumerate(values) if index != best)
    return best if values[best] - others >= TAB_MARGIN else None


def row_occupied(picture, row):
    """True if the row (0 top, 1 second) shows a vessel (its orange wireframe picture), False if it looks empty."""
    if picture is None or getattr(picture, "ndim", 0) != 3:
        return None
    height, width = picture.shape[:2]
    x0 = int(width / 2.0 + ROW_ART_X[0] * height)
    x1 = int(width / 2.0 + ROW_ART_X[1] * height)
    y0, y1 = int(ROW_ART_Y[row][0] * height), int(ROW_ART_Y[row][1] * height)
    step = max(1, height // 270)
    cell = picture[y0:y1:step, x0:x1:step].astype("int16")
    red, green, blue = cell[..., 0], cell[..., 1], cell[..., 2]
    count = int(((red >= 70) & (green >= 25) & (green <= 210) & (blue <= 70) & (red > green + 20)).sum())
    return count >= ROW_ART_MIN


def describe(picture):
    """One line for the log."""
    bar, tab = lit_button(picture), selected_tab(picture)
    return "role tab=%s lit=%s grey=%d rows=%s/%s" % (
        TABS[tab] if tab is not None else "?",
        "row%d(y=%.2f)" % (bar["row"] + 1, bar["y"]) if bar else "none", len(grey_buttons(picture)),
        row_occupied(picture, 0), row_occupied(picture, 1))


def map_png(picture, path):
    """Saves a small 'what is where' map of the role panel (about 480 pixels wide, NO game picture): white = lit amber button or the
    selected tab fill, light grey = greyed-out button, dark grey = ordinary orange panel drawing. Shows which row the cursor is on
    when a look fails. Returns True if it was written."""
    try:
        import numpy as np
        from PIL import Image
        small, _ = _small(picture)
        out = np.zeros(small.shape[:2], dtype=np.uint8)
        red, green, blue = small[..., 0], small[..., 1], small[..., 2]
        out[(red >= 70) & (green >= 25) & (blue <= 70) & (red > green + 20)] = 70
        out[_grey(small)] = 150
        out[_amber(small)] = 255
        Image.fromarray(out).save(str(path))
        return True
    except Exception:
        return False
