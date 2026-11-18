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
        self.time_scale = 1.0         # stretches the mouth track so it ends when the real sound ends
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
        self.fx_beam = True           # sparks rising from the ring and orbiting her chest (gives her depth)
        self.fx_turn = True           # she turns a few degrees left and right (fake 3D)
        self.first_frame = True

    # ---- what happens ----
    def speech_started(self, text, now=None):
        now = self.clock() if now is None else now
        self.line_text = str(text or "")
        self.track = build_track(self.line_text, self.cps)
        self.track_start, self.speaking = now, True
        self.time_scale = 1.0

    def set_duration(self, seconds):
        """The real length of the sound is known: stretch or squeeze the mouth so it finishes exactly when she does."""
        length = track_length(self.track)
        if length > 0 and seconds and seconds > 0:
            self.time_scale = max(0.4, min(3.0, float(seconds) / length))

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
            elapsed = (now - self.track_start) / self.time_scale
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
        if self.fx_turn:
            frame = self._turn(frame, now)
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
        if self.flicker_on and now < self.glitch_until:                       # a short torn-picture glitch: only HER picture tears
            for y, h, dx in self.strips:
                out[y:y + h] = np.roll(out[y:y + h], dx, axis=1)
        steady = max(0.0, min(1.0, self.power))                                # the rings and the lights do not flicker, only she does
        ring = a.rings * (0.8 * steady)
        ring_colour = (np.array([70.0, 180.0, 255.0], dtype=np.float32) @ tint_matrix(self.mix).T)
        out = np.maximum(out, ring * ring_colour)
        if self.fx_beam:
            near = np.zeros((a.window_h, a.window_w), dtype=np.float32)
            far = np.zeros_like(near)
            self._sparks(now, near, far)
            strength = steady
            body = out.max(axis=2, keepdims=True) / 90.0                              # her picture hides the far half of the loops
            far = far[..., None] * np.clip(1.0 - body, 0.0, 1.0)
            glow = np.array([225.0, 245.0, 255.0], dtype=np.float32) @ tint_matrix(self.mix).T
            out = np.maximum(out, far * glow * strength)
            out = np.maximum(out, near[..., None] * glow * strength)
        if self.moving:
            out = self._move_frame(out)
        pixels = out.astype(np.uint8)
        dark = pixels.max(axis=2) <= THRESHOLD
        pixels[dark] = KEY
        return pixels

    def _depth_map(self):
        """A rough 'how close to you' map for the picture (face and chest nearest), made once. Only used for the gentle turning."""
        a = self.assets
        if getattr(self, "_depth", None) is None or self._depth.shape != (a.height, a.width):
            ys, xs = np.mgrid[0:a.height, 0:a.width].astype(np.float32)
            cx = a.width / 2.0
            face = np.exp(-(((xs - cx) / (a.width * 0.17)) ** 2 + ((ys - a.height * 0.27) / (a.height * 0.17)) ** 2))
            chest = np.exp(-(((xs - cx) / (a.width * 0.30)) ** 2 + ((ys - a.height * 0.72) / (a.height * 0.22)) ** 2)) * 0.7
            hair = np.exp(-(((xs - cx) / (a.width * 0.5)) ** 2 + ((ys - a.height * 0.4) / (a.height * 0.5)) ** 2)) * 0.25
            self._depth = np.clip(face + chest + hair, 0.0, 1.0)
        return self._depth

    def _turn(self, frame, now):
        """Slide near parts (face, chest) a little more than far parts (hair edges), left and right, so she seems to turn on the spot."""
        a = self.assets
        swing = math.sin(now * 0.55) * 0.5 + math.sin(now * 0.23 + 1.0) * 0.3        # slow and never quite repeating
        amount = swing * a.width * 0.022
        if abs(amount) < 0.05:
            return frame
        shift = (self._depth_map() - 0.4) * amount                                    # pixels, per pixel
        w = a.width
        cols = np.arange(w, dtype=np.float32)[None, :] - shift                        # where each output pixel looks in the picture
        left = np.clip(np.floor(cols).astype(np.int32), 0, w - 1)
        right = np.clip(left + 1, 0, w - 1)
        frac = (cols - np.floor(cols))[..., None]
        rows = np.arange(a.height)[:, None]
        return frame[rows, left] * (1.0 - frac) + frame[rows, right] * frac

    def _sparks(self, now, front, behind):
        """A slow tornado of tiny lights. Every light has its own random life: where it is born, how fast it climbs, how fast it swirls, how
        wide it goes and how bright it is, and it picks new random values each time it is reborn. They start in the middle of the lower ring,
        spiral up round her (narrow low down, wider higher up) and fade out at the height of her chest, never higher. The far half of each turn
        goes behind her (dimmer), the near half in front."""
        a = self.assets
        cx = a.window_w / 2.0
        y_ring = PAD_TOP + a.height + 14.0
        y_top = PAD_TOP + a.height * 0.64                                              # the top of her chest: nothing goes higher than this
        radius = a.window_w * 0.40
        count = 450
        i = np.arange(count, dtype=np.float64)

        def rnd(cycle, salt):
            value = np.sin(i * 12.9898 + cycle * 78.233 + salt * 37.719) * 43758.5453
            return (value - np.floor(value)).astype(np.float32)

        period = 5.0 + 7.0 * rnd(0.0, 1.0)                                              # each light climbs at its own speed (5 to 12 seconds)
        clock = now / period + rnd(0.0, 2.0)                                            # and starts at its own moment
        cycle = np.floor(clock)
        progress = (clock - cycle).astype(np.float32)
        angle = rnd(cycle, 3.0) * 6.2832 + progress * (1.0 + 4.0 * rnd(cycle, 4.0)) * 6.2832 * 0.6 * np.where(rnd(0.0, 5.0) < 0.85, 1.0, -1.0)
        wide = 0.25 + 0.95 * rnd(cycle, 6.0)                                           # how wide this light swirls
        r = radius * wide * progress ** 0.8
        sway = 1.0 + 0.15 * np.sin(now * 1.7 + i)                                       # a little wobble so none move in a pure curve
        x = cx + r * np.cos(angle) * sway
        y = y_ring + (y_top - y_ring) * progress + r * 0.2 * np.sin(angle)
        fade = np.minimum(1.0, progress * 10.0) * np.clip((1.0 - progress) * 3.0, 0.0, 1.0)
        near = np.sin(angle) > 0
        bright = 0.25 + 0.75 * rnd(cycle, 7.0) ** 1.5                                   # mostly faint, a few brighter
        strength = fade * bright * np.where(near, 1.0, 0.5)
        ix = np.rint(x).astype(np.int32)
        iy = np.rint(y).astype(np.int32)
        ok = (iy >= int(math.ceil(y_top))) & (ix >= 0) & (ix < a.window_w) & (iy >= 0) & (iy < a.window_h)
        for layer, pick in ((front, ok & near), (behind, ok & ~near)):
            np.maximum.at(layer, (iy[pick], ix[pick]), strength[pick])

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
