"""
The maths behind the Overlays page: where each overlay box sits on a picture of your screen, and what to save when you drag it.

Every overlay stores its place its own way (gap from the left or the right, from the top or the bottom, in percent of the screen),
so each is described once in BOXES and everything else works from that. Nothing here needs a window, so it is all tested.
"""

from PIL import Image, ImageDraw

from ui import bio_overlay, hologram, route_overlay

REFERENCE_PICTURE = 784 / 1168.0         # her still picture: width / height


class Box:
    def __init__(self, key, label, colour, h_edge, h_key, v_edge, v_key, switch=None):
        self.key, self.label, self.colour = key, label, colour
        self.h_edge, self.h_key = h_edge, h_key      # "left" or "right", and the setting that holds the gap in percent
        self.v_edge, self.v_key = v_edge, v_key      # "top" or "bottom"
        self.switch = switch                         # the setting that turns it on (None = always listed)


BOXES = (
    Box("hologram", "Her hologram", "#35d6ff", "left", "hologram.left", "bottom", "hologram.bottom", "hologram.enabled"),
    Box("bio", "Biology list", "#ff9a1f", "left", "overlay.bio_x", "bottom", "overlay.bio_up", "overlay.bio_enabled"),
    Box("route", "Route map", "#5aa7ff", "right", "overlay.route_right", "top", "overlay.route_top", None),
    Box("pin", "Chat comment", "#f5a623", "left", "streaming.pin_x", "bottom", "streaming.pin_up", "streaming.pin_overlay"),
)
DEFAULTS = {"hologram.left": 6.5, "hologram.bottom": 24.0, "overlay.bio_x": 3, "overlay.bio_up": 25,
            "overlay.route_right": 2, "overlay.route_top": 10, "streaming.pin_x": 2.0, "streaming.pin_up": 8.0}
MAX_PERCENT = 95.0


def box_for(key):
    for box in BOXES:
        if box.key == key:
            return box
    raise KeyError(key)


def size_pixels(box, settings, screen_w, screen_h):
    """About how big the box is on the real screen, in pixels (width, height). Close enough to drag by; the overlays size themselves."""
    if box.key == "hologram":
        h = hologram.height_for(screen_h, settings.get("hologram.size", 100))
        return int(h * REFERENCE_PICTURE), h
    if box.key == "bio":
        size = bio_overlay.SIZES.get(str(settings.get("overlay.bio_size", "Medium")), 12)
        return int(size * 23), int(size * 2.0 + size * 2.3 * 3 + 10)
    if box.key == "pin":
        from ui import chat_pin_overlay
        width = int(screen_w * chat_pin_overlay.WIDTH_SHARE.get(str(settings.get("streaming.pin_size", "Medium")), 0.34))
        return width, int(width * 0.22)
    size = route_overlay.map_size(settings.get("overlay.route_size", "Medium"))
    return size, size + 70


def _gap(settings, key):
    try:
        value = float(settings.get(key, DEFAULTS[key]))
    except (TypeError, ValueError):
        value = float(DEFAULTS[key])
    return min(MAX_PERCENT, max(0.0, value))


def rect(box, settings, screen_w, screen_h):
    """Where the box is, as fractions of the screen: (x, y, w, h) measured from the top left."""
    w, h = size_pixels(box, settings, screen_w, screen_h)
    w, h = min(w, screen_w), min(h, screen_h)
    gx, gy = _gap(settings, box.h_key) / 100.0, _gap(settings, box.v_key) / 100.0
    x = screen_w * gx if box.h_edge == "left" else screen_w - screen_w * gx - w
    y = screen_h * gy if box.v_edge == "top" else screen_h - screen_h * gy - h
    x, y = max(0, min(x, screen_w - w)), max(0, min(y, screen_h - h))
    return x / screen_w, y / screen_h, w / screen_w, h / screen_h


def settings_for(box, x, y, w, h):
    """What to save when the box's top-left corner is dropped at (x, y) (fractions of the screen) and it is w by h big."""
    x = max(0.0, min(x, 1.0 - w))
    y = max(0.0, min(y, 1.0 - h))
    gx = 100.0 * (x if box.h_edge == "left" else 1.0 - x - w)
    gy = 100.0 * (y if box.v_edge == "top" else 1.0 - y - h)
    return {box.h_key: round(min(MAX_PERCENT, max(0.0, gx)), 1), box.v_key: round(min(MAX_PERCENT, max(0.0, gy)), 1)}


def cockpit_picture(width, height):
    """A simple drawing of a cockpit view, so there is something to line the boxes up against. Use your own screenshot for the real thing."""
    img = Image.new("RGB", (width, height), (6, 8, 16))
    d = ImageDraw.Draw(img)
    for i in range(0, height, 2):                                   # space, a little lighter near the middle
        shade = int(14 + 18 * (1 - abs(i - height * 0.4) / (height * 0.6)))
        d.line([(0, i), (width, i)], fill=(shade // 2, shade // 2, shade + 6))
    for k in range(60):                                             # a few stars, always in the same places
        x, y = (k * 97) % width, (k * 53) % int(height * 0.6)
        d.point((x, y), fill=(160, 170, 200))
    d.ellipse([int(width * 0.60), int(height * 0.12), int(width * 0.74), int(height * 0.12) + int(width * 0.14)], fill=(60, 48, 40))
    frame = (22, 24, 32)
    d.polygon([(0, 0), (int(width * 0.10), 0), (int(width * 0.03), int(height * 0.62)), (0, int(height * 0.72))], fill=frame)
    d.polygon([(width, 0), (int(width * 0.90), 0), (int(width * 0.97), int(height * 0.62)), (width, int(height * 0.72))], fill=frame)
    d.polygon([(0, int(height * 0.72)), (int(width * 0.03), int(height * 0.62)), (int(width * 0.97), int(height * 0.62)), (width, int(height * 0.72)),
               (width, height), (0, height)], fill=(18, 20, 28))
    d.rectangle([int(width * 0.30), int(height * 0.78), int(width * 0.70), int(height * 0.97)], outline=(70, 48, 20), width=2)
    d.ellipse([int(width * 0.04), int(height * 0.70), int(width * 0.18), int(height * 0.70) + int(width * 0.14)], outline=(70, 48, 20), width=2)
    d.ellipse([int(width * 0.82), int(height * 0.70), int(width * 0.96), int(height * 0.70) + int(width * 0.14)], outline=(70, 48, 20), width=2)
    d.line([(width // 2 - 12, int(height * 0.40)), (width // 2 + 12, int(height * 0.40))], fill=(120, 90, 40), width=1)
    d.line([(width // 2, int(height * 0.40) - 12), (width // 2, int(height * 0.40) + 12)], fill=(120, 90, 40), width=1)
    return img
