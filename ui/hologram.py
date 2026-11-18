"""
Her hologram: a small see-through picture of her above the left panel of the cockpit that talks, blinks and changes colour.

Two parts, like the route map:
  * THIS FILE is plain Python and numpy. It decides what the picture looks like right now (colour, power, mouth) and draws it
    into an array of pixels. All of it is unit-tested, so it can be trusted without a screen.
  * ui/hologram_window.py is the tkinter window that shows the pixels (see-through, click-through, draggable).

What she looks like:
  cyan   = ordinary (the picture's own blue)
  green  = she is listening for you (push-to-talk held, her name heard and she is waiting, or she has asked you a question).
           With the microphone simply always open she stays cyan: green would mean nothing.
  amber  = she is thinking (the optional AI chat is working on an answer)
  Powered down (a ghost, then gone) while any other game screen is open (panels, maps, station menus); powers up with a flicker.
  Her mouth follows what she says: the text is turned into mouth pictures (open, round, lips together, teeth on lip...) and timed
  to how fast her voice has been speaking. It does not listen to the sound itself, so it cannot be out of step for long.

The window is see-through with ONE exact colour (KEY), the same way the route map is, so anything darker than THRESHOLD becomes
see-through: the picture's black background simply disappears.
"""

import json
import math
import random
import time
from pathlib import Path

import numpy as np

from core.logger import get_logger

log = get_logger("hologram")

ASSET_DIR = Path(__file__).resolve().parent / "assets" / "hologram"
KEY = (1, 2, 3)                  # this exact colour becomes see-through
KEY_HEX = "#010203"
THRESHOLD = 24                   # anything with no channel brighter than this is see-through
BASE_HEIGHT = 225                # pixels tall at 100% on a 1080-pixel-high screen
PAD_TOP, PAD_BOTTOM = 8, 30      # room for her to float up and down, and for the rings she stands on
PICTURE_ASPECT = 784 / 1168

# ---- colours: the picture is blue; green and amber are the same picture with its colours turned ----
HUE = {"cyan": 0.0, "green": -72.0, "amber": 197.0}
LISTEN_SECONDS = 6.0             # after her name on its own she waits this long for the rest
COLOUR_SECONDS = 0.35            # how long a colour change takes
DOWN_SECONDS, UP_SECONDS = 0.35, 0.6
GHOST = 0.0                      # powered down = fully gone (the window hides)

# ---- mouth ----
VOWEL = {"a": "ah", "e": "eh", "i": "eh", "y": "eh", "o": "oh", "u": "oo", "w": "oo",
         "m": "pressed", "b": "pressed", "p": "pressed", "f": "fv", "v": "fv",
         "s": "eh", "t": "eh", "d": "eh", "n": "eh", "z": "eh", "c": "eh"}
MOUTH_SPRITES = ("pressed", "eh", "ah", "oh", "oo", "ee", "smile", "fv")
BIGGEST = {"ah": 1.0, "oh": 0.9, "eh": 0.85, "ee": 0.9, "oo": 0.9}      # how much "open" each needs (see MouthShape.weights)
DEFAULT_CPS = 13.0               # letters per second, until she has spoken a few lines and we know better
SMILE_SECONDS = 1.8


def hue_matrix(degrees):
    """A 3 x 3 colour matrix that turns every colour by this many degrees (0 = no change)."""
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return np.array([[.213 + c * .787 - s * .213, .715 - c * .715 - s * .715, .072 - c * .072 + s * .928],
                     [.213 - c * .213 + s * .143, .715 + c * .285 + s * .140, .072 - c * .072 - s * .283],
                     [.213 - c * .213 - s * .787, .715 - c * .715 + s * .715, .072 + c * .928 + s * .072]], dtype=np.float32)


def tint_matrix(mix):
    """The colour matrix for a mix of {'cyan': 1.0, 'green': 0.0, 'amber': 0.0} (the weights add up to 1)."""
    total = sum(max(0.0, mix.get(name, 0.0)) for name in HUE) or 1.0
    out = np.zeros((3, 3), dtype=np.float32)
    for name, degrees in HUE.items():
        out += (max(0.0, mix.get(name, 0.0)) / total) * hue_matrix(degrees)
    return out


# ---- the mouth ----
def build_track(text, cps=DEFAULT_CPS):
    """What her mouth does while she says this text: a list of (start, end, picture or None) in seconds from the start of the line."""
    letter = 1.0 / max(4.0, float(cps))
    track, t = [], 0.0
    clean = str(text or "").replace("||", ", ")
    for ch in clean.lower():
        if ch == " ":
            length, shape = letter * 0.6, None
        elif ch in ",;:":
            length, shape = letter * 3.0, None
        elif ch in ".!?":
            length, shape = letter * 5.0, None
        elif ch.isalpha():
            length, shape = letter, VOWEL.get(ch)
        else:
            continue
        track.append((t, t + length, shape))
        t += length
    return track


def track_length(track):
    return track[-1][1] if track else 0.0


def shape_at(track, elapsed):
    for start, end, shape in track:
        if start <= elapsed < end:
            return shape
    return None


def reach(open_fraction, name):
    """How strongly to show a mouth picture. open_fraction = 1.0 is the full wide-open picture, lower is a softer, smaller mouth."""
    big = BIGGEST.get(name)
    if big is None:
        return 1.0
    return max(0.0, min(1.0, open_fraction / big + (1.0 - open_fraction) * 0.15))


class Assets:
    """The base picture and the mouth and eye cut-outs, resized once to the size she will be shown at."""

    def __init__(self, height, directory=None):
        directory = Path(directory) if directory else ASSET_DIR
        from PIL import Image
        meta = json.loads((directory / "hologram.json").read_text(encoding="utf-8"))
        src_w, src_h = meta["size"]
        self.height = max(40, int(height))
        self.width = max(20, int(round(self.height * src_w / src_h)))
        scale = self.height / float(src_h)
        base = Image.open(directory / meta["base"]).convert("RGB").resize((self.width, self.height), Image.LANCZOS)
        self.base = np.asarray(base, dtype=np.float32)
        self.sprites = {}
        for name, (ox, oy) in meta["sprites"].items():
            picture = Image.open(directory / ("%s.png" % name)).convert("RGBA")
            w, h = max(1, int(round(picture.width * scale))), max(1, int(round(picture.height * scale)))
            picture = np.asarray(picture.resize((w, h), Image.LANCZOS), dtype=np.float32)
            x, y = int(round(ox * scale)), int(round(oy * scale))
            self.sprites[name] = (x, y, picture[..., :3], picture[..., 3:4] / 255.0)
        self.window_w = self.width
        self.window_h = self.height + PAD_TOP + PAD_BOTTOM
        self.rings = self._rings()

    def _rings(self):
        """The two glowing rings she stands on, as a 0..1 strength per pixel in window coordinates."""
        from PIL import Image, ImageDraw
        layer = Image.new("L", (self.window_w, self.window_h), 0)
        draw = ImageDraw.Draw(layer)
        cx, cy = self.window_w // 2, PAD_TOP + self.height + 14
        for fraction, level in ((0.46, 235), (0.32, 140)):
            rx = int(self.window_w * fraction)
            ry = max(3, int(rx * 0.2))
            draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), outline=level, width=2)
        return np.asarray(layer, dtype=np.float32)[..., None] / 255.0


class Hologram:
    """What she looks like right now. Feed it facts (tick), then ask for the pixels (render)."""

    def __init__(self, assets, rng=None, clock=time.monotonic):
        self.assets = assets
        self.rng = rng or random.Random()
        self.clock = clock
        now = clock()
        self.mix = {"cyan": 1.0, "green": 0.0, "amber": 0.0}
        self.power = 0.0
        self.weights = {name: 0.0 for name in assets.sprites}
        self.track, self.track_start, self.speaking = [], 0.0, False
        self.line_text, self.cps = "", DEFAULT_CPS
        self.listen_until = 0.0
        self.smile_until = 0.0
        self.blink_at, self.blink_until = now + 3.0, 0.0
        self.last = now
        self.flicker_until = 0.0
        self.glitch_until, self.next_glitch = 0.0, now + 3.0
        self.strips = []
        self.moving = False          # "Move her" is on: draw a frame so she can be grabbed
        self.open_fraction = 0.55
        self.flicker_on = True
        self.first_frame = True

    # ---- what happens ----
    def speech_started(self, text, now=None):
        now = self.clock() if now is None else now
        self.line_text = str(text or "")
        self.track = build_track(self.line_text, self.cps)
        self.track_start, self.speaking = now, True

    def speech_finished(self, now=None):
        now = self.clock() if now is None else now
        took = now - self.track_start
        letters = sum(1 for ch in self.line_text if ch.isalpha())
        if self.speaking and took > 0.6 and letters >= 8:
            measured = letters / took                           # learn how fast this voice really speaks
            self.cps = max(8.0, min(22.0, 0.6 * self.cps + 0.4 * measured))
        self.speaking = False
        self.smile_until = now + SMILE_SECONDS

    def heard_her_name(self, now=None):
        """Her name was said on its own: she is waiting for the rest."""
        now = self.clock() if now is None else now
        self.listen_until = now + LISTEN_SECONDS

    # ---- one step ----
    def colour_wanted(self, listening, thinking, now):
        if thinking:
            return "amber"
        if listening or now < self.listen_until:
            return "green"
        return "cyan"

    def tick(self, listening=False, thinking=False, powered=True, now=None):
        """Move everything a little towards where it should be. Returns how visible she is (0 = hidden)."""
        now = self.clock() if now is None else now
        dt = max(0.0, min(0.25, now - self.last))
        self.last = now
        wanted = self.colour_wanted(listening, thinking, now)
        step = dt / COLOUR_SECONDS
        for name in self.mix:
            goal = 1.0 if name == wanted else 0.0
            self.mix[name] += max(-step, min(step, goal - self.mix[name]))
        goal_power = 1.0 if powered else 0.0
        if self.first_frame:
            self.first_frame = False
        rate = dt / (UP_SECONDS if goal_power > self.power else DOWN_SECONDS)
        self.power += max(-rate, min(rate, goal_power - self.power))
        mouth = self._mouth_goal(now)
        for name in self.weights:
            if name == "eyes":
                goal = 1.0 if now < self.blink_until else 0.0
                speed = 0.035
            else:
                goal = 1.0 if name == mouth else 0.0
                speed = 0.055
            self.weights[name] += (goal - self.weights[name]) * min(1.0, dt / speed)
        if now >= self.blink_at:
            self.blink_until = now + 0.15
            self.blink_at = now + 2.4 + self.rng.random() * 3.2
        if self.flicker_on and now >= self.next_glitch:
            self.glitch_until = now + 0.14
            self.next_glitch = now + 2.8 + self.rng.random() * 3.2
            self.strips = [(self.rng.randint(0, max(1, self.assets.window_h - 20)), self.rng.randint(4, 22),
                            self.rng.randint(-8, 8)) for _ in range(5)]
        return self.power

    def _mouth_goal(self, now):
        if self.speaking:
            elapsed = now - self.track_start
            if elapsed > track_length(self.track) + 0.4:
                return None
            return shape_at(self.track, elapsed)
        if now < self.smile_until:
            return "smile"
        return None

    # ---- the pixels ----
    def render(self, now=None):
        """The picture as an (h, w, 3) uint8 array in window size. See-through pixels are exactly KEY."""
        now = self.clock() if now is None else now
        a = self.assets
        frame = a.base.copy()
        for name, weight in self.weights.items():
            if weight < 0.02 or name not in a.sprites:
                continue
            x, y, rgb, alpha = a.sprites[name]
            strength = min(1.0, weight) * (reach(self.open_fraction, name) if name != "eyes" else 1.0)
            h, w = rgb.shape[:2]
            region = frame[y:y + h, x:x + w]
            rh, rw = region.shape[:2]
            if rh <= 0 or rw <= 0:
                continue
            blend = alpha[:rh, :rw] * strength
            region[:] = region * (1.0 - blend) + rgb[:rh, :rw] * blend
        # scan lines and the bright sweep
        frame[::3] *= 0.84
        sweep = int((now * 70.0) % (a.height * 1.6)) - int(a.height * 0.2)
        lo, hi = max(0, sweep - 7), min(a.height, sweep + 7)
        if hi > lo:
            frame[lo:hi] *= 1.0 + 0.25 * np.hanning(hi - lo + 2)[1:-1, None, None]
        # a slow breathing flicker, and a rougher one while she powers up or down
        level = self.power
        if self.flicker_on:
            level *= 0.95 + 0.05 * math.sin(now * 23.0) * math.sin(now * 7.3)
            if 0.02 < self.power < 0.98:
                level *= 0.55 + 0.45 * self.rng.random()
        frame *= max(0.0, min(1.0, level))
        # colour
        frame = frame @ tint_matrix(self.mix).T
        np.clip(frame, 0, 255, out=frame)
        # into the window: padded, floating up and down a pixel or two, with her rings under her
        bob = int(round(math.sin(now * 1.3) * 2.0)) if self.flicker_on else 0
        out = np.zeros((a.window_h, a.window_w, 3), dtype=np.float32)
        top = PAD_TOP + bob
        out[top:top + a.height] = frame
        ring = a.rings * (0.8 * max(0.0, min(1.0, level)))
        ring_colour = (np.array([70.0, 180.0, 255.0], dtype=np.float32) @ tint_matrix(self.mix).T)
        out = np.maximum(out, ring * ring_colour)
        if self.flicker_on and now < self.glitch_until:                       # a short torn-picture glitch
            for y, h, dx in self.strips:
                out[y:y + h] = np.roll(out[y:y + h], dx, axis=1)
        if self.moving:
            out = self._move_frame(out)
        pixels = out.astype(np.uint8)
        dark = pixels.max(axis=2) <= THRESHOLD
        pixels[dark] = KEY
        return pixels

    def _move_frame(self, out):
        """A thin cyan frame while "Move her" is on: something solid to grab."""
        h, w = out.shape[:2]
        colour = np.array([90.0, 200.0, 255.0], dtype=np.float32)
        out[:2, :] = colour
        out[-2:, :] = colour
        out[:, :2] = colour
        out[:, -2:] = colour
        return out

    def visible(self):
        return self.power > 0.03


def height_for(screen_height, size_percent):
    """How many pixels tall she is on this screen (225 on a 1080-pixel-high screen at 100%)."""
    size = max(40.0, min(200.0, float(size_percent or 100)))
    return max(80, int(round(BASE_HEIGHT * (float(screen_height) / 1080.0) * size / 100.0)))


def window_position(screen_w, screen_h, win_w, win_h, left_percent, bottom_percent):
    """Top-left corner of her window: left_percent = gap from the left edge, bottom_percent = gap from the bottom."""
    left = min(95.0, max(0.0, float(left_percent)))
    bottom = min(95.0, max(0.0, float(bottom_percent)))
    x = int(screen_w * left / 100.0)
    y = int(screen_h - screen_h * bottom / 100.0 - win_h)
    return max(0, min(x, screen_w - win_w)), max(0, min(y, screen_h - win_h))


def percents_from_position(screen_w, screen_h, win_w, win_h, x, y):
    """The opposite of window_position: what to save after she has been dragged."""
    left = 100.0 * max(0, min(x, screen_w - win_w)) / max(1, screen_w)
    bottom = 100.0 * max(0, screen_h - (y + win_h)) / max(1, screen_h)
    return round(min(95.0, left), 1), round(min(95.0, bottom), 1)
