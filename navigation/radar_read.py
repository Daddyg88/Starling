"""RADAR READER (0.96.3): finds the icons on the on-foot radar (top-left of the screen) and turns them into real positions on the planet.

What the radar shows (checked on real pictures from Ben's PC): you in the middle, the radar turned so UP is the way you face, and small icons for
  terminals (a cyan monitor), ammo points (three cyan bars), recharge points (a yellow bolt), gun posts (a green T-shaped figure) and
  people (green arrows, which MOVE, so they are ignored).
It sees about 50 metres. The picture is squashed a little (a metre sideways is about 9% more pixels than a metre forward).

How: the radar corner is shrunk or grown to a fixed size (355 x 308), each icon colour is turned into a black-and-white map, and each
icon shape is looked for with a normalised correlation (numpy only: no OpenCV). The offset of an icon from you, your heading and your
position (Status.json) give its latitude and longitude. Repeats of the same icon seen from different places agree to about 3 metres.

Nothing here touches the game. The picture is thrown away; only the positions are kept (navigation/radar_points.py).
"""
import math
from pathlib import Path

from core.logger import get_logger

log = get_logger("radar_read")

REF_BOX = (67, 38, 422, 346)          # the radar corner on a 1920 x 1080 screen: left, top, right, bottom
REF_SIZE = (REF_BOX[2] - REF_BOX[0], REF_BOX[3] - REF_BOX[1])      # (355, 308)
ORIGIN = (186.0, 165.0)               # where YOU are inside the crop (pixels), fitted to real walks
PIXELS_PER_METRE = (2.4, 2.2)         # sideways, forward (the radar is squashed)
ELLIPSE = (140.0, 120.0)              # the radar's edge around you (pixels), a little generous
CENTRE = (182.0, 165.0)               # the middle of the radar's edge
ICONS = ("terminal", "ammo", "recharge", "turret")
COLOUR_OF = {"terminal": "cyan", "ammo": "cyan", "recharge": "yellow", "turret": "green"}
MIN_SCORE = {"terminal": 0.47, "ammo": 0.50, "recharge": 0.55, "turret": 0.78}      # turret high: a person (green arrow) looks a little like one
YOU = (185, 170)                      # your own arrow in the middle looks a little like an ammo box: icons right on it need a better match
HALF = 10                             # the icon pictures are 21 x 21
ICON_DIR = Path(__file__).resolve().parent / "radar_icons"

_templates = {}


def crop_box(width, height):
    """(left, top, right, bottom) of the radar in a screen of this size. The HUD is anchored to the top-left corner and scales with the
    screen HEIGHT, so any 16:9 (and wider) screen works; the box is cut off at the picture's edge."""
    scale = height / 1080.0
    left, top, right, bottom = (int(round(v * scale)) for v in REF_BOX)
    return left, top, min(right, width), min(bottom, height)


def colour_masks(rgb):
    """Black-and-white maps (True = this colour) of the three icon colours, from an H x W x 3 picture."""
    import numpy as np
    a = rgb.astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return {"cyan": (g > 185) & (b > 190) & (r < 180),
            "yellow": (r > 200) & (g > 170) & (b < 110),
            "green": (g > 200) & (r < 150) & (b < 120)}


def _template(name):
    import numpy as np
    from PIL import Image
    if name not in _templates:
        t = (np.asarray(Image.open(ICON_DIR / ("%s.png" % name)).convert("L")) > 127).astype(np.float32)
        centred = t - t.mean()
        _templates[name] = (centred, float(np.sqrt((centred ** 2).sum())))
    return _templates[name]


def _correlate(mask, name):
    """Normalised correlation of an icon shape with every place in the mask (numpy FFT). Returns an array the size of the mask."""
    import numpy as np
    template, norm = _template(name)
    image = mask.astype(np.float32)
    h, w = image.shape
    th, tw = template.shape
    size = (h + th, w + tw)
    top = np.fft.irfft2(np.fft.rfft2(image, size) * np.conj(np.fft.rfft2(template, size)), size)
    top = top[:h, :w]                                           # numerator for a template whose top-left corner is at (y, x)
    ones = np.ones((th, tw), dtype=np.float32)
    n = float(th * tw)
    csum = np.pad(image, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    csq = np.pad(image * image, ((1, 0), (1, 0))).cumsum(0).cumsum(1)

    def box(c):
        return c[th:, tw:] - c[:-th, tw:] - c[th:, :-tw] + c[:-th, :-tw]
    window_sum, window_sq = box(csum), box(csq)                  # for windows whose top-left is (y, x), size (h-th+1, w-tw+1)
    variance = np.maximum(window_sq - window_sum * window_sum / n, 1e-6)
    out = np.zeros((h, w), dtype=np.float32)
    score = top[:h - th + 1, :w - tw + 1] / (np.sqrt(variance) * max(norm, 1e-6))
    out[HALF:HALF + score.shape[0], HALF:HALF + score.shape[1]] = score         # index by the icon's CENTRE
    return out


def _peaks(score, threshold, gap=9):
    """Best-first local maxima above the threshold, no two closer than `gap` pixels."""
    import numpy as np
    found = []
    work = score.copy()
    for _ in range(40):
        y, x = np.unravel_index(int(np.argmax(work)), work.shape)
        best = float(work[y, x])
        if best < threshold:
            break
        found.append((int(x), int(y), best))
        work[max(0, y - gap):y + gap + 1, max(0, x - gap):x + gap + 1] = -1.0
    return found


def inside_radar(x, y):
    return ((x - CENTRE[0]) / ELLIPSE[0]) ** 2 + ((y - CENTRE[1]) / ELLIPSE[1]) ** 2 <= 1.0


def normalise(picture):
    """A numpy RGB crop of the radar (any size) -> the fixed 355 x 308 size, as a numpy array."""
    import numpy as np
    from PIL import Image
    if picture.shape[1] == REF_SIZE[0] and picture.shape[0] == REF_SIZE[1]:
        return picture
    image = Image.fromarray(picture).resize(REF_SIZE, Image.BILINEAR)
    return np.asarray(image)


def find_icons(crop):
    """Every icon on the radar crop: [{"kind", "x", "y", "score"}] with x, y in the fixed 355 x 308 crop pixels."""
    rgb = normalise(crop)
    masks = colour_masks(rgb)
    found = []
    for kind in ICONS:
        mask = masks[COLOUR_OF[kind]]
        if int(mask.sum()) < 15:
            continue
        for x, y, score in _peaks(_correlate(mask, kind), MIN_SCORE[kind]):
            if abs(x - YOU[0]) < 7 and abs(y - YOU[1]) < 7 and score < 0.75:
                continue
            if inside_radar(x, y):
                found.append({"kind": kind, "x": x, "y": y, "score": round(score, 2)})
    # the same cyan blob can look a little like both a terminal and an ammo box: keep the better one (a real ammo box right beside a terminal is kept)
    keep = []
    for icon in sorted(found, key=lambda i: -i["score"]):
        if any(abs(icon["x"] - k["x"]) < 5 and abs(icon["y"] - k["y"]) < 5 for k in keep):
            continue
        keep.append(icon)
    return keep


def offset_metres(icon):
    """(right, forward) in metres of an icon from you."""
    return (icon["x"] - ORIGIN[0]) / PIXELS_PER_METRE[0], -(icon["y"] - ORIGIN[1]) / PIXELS_PER_METRE[1]


def to_position(icon, latitude, longitude, heading, radius):
    """The icon's latitude and longitude (degrees), from where you stand and which way you face (degrees, 0 = north, 90 = east).
    radius = the planet's radius in metres (Status.json PlanetRadius). None when something is missing."""
    if None in (latitude, longitude, heading, radius) or not radius:
        return None
    right, forward = offset_metres(icon)
    t = math.radians(heading)
    north = -right * math.sin(t) + forward * math.cos(t)
    east = right * math.cos(t) + forward * math.sin(t)
    per_degree = math.pi / 180.0 * radius
    return (latitude + north / per_degree,
            longitude + east / (per_degree * max(0.05, math.cos(math.radians(latitude)))))


def metres_between(a, b, radius):
    """Distance in metres between two (lat, lon) points on a planet of this radius (small distances)."""
    per_degree = math.pi / 180.0 * radius
    north = (a[0] - b[0]) * per_degree
    east = (a[1] - b[1]) * per_degree * math.cos(math.radians((a[0] + b[0]) / 2.0))
    return math.hypot(north, east)
