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
import re
import threading
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
LIVE_SHAPES = ("ah", "oh", "eh", "oo", "ee", "fv")      # the mouth pictures that open and close with the real loudness
TURN_SHIFT = 0.055                # how far she turns: the nearest parts slide this fraction of her width
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
         "s": "soft", "t": "soft", "d": "soft", "n": "soft", "z": "soft", "c": "soft", "l": "soft"}
MOUTH_SPRITES = ("pressed", "eh", "ah", "oh", "oo", "ee", "smile", "fv")
BIGGEST = {"ah": 1.0, "oh": 0.9, "eh": 0.85, "ee": 0.9, "oo": 0.9}      # how much "open" each needs (see MouthShape.weights)
DEFAULT_CPS = 13.0               # letters per second, until she has spoken a few lines and we know better
SMILE_SECONDS = 1.8
# softer, more natural lips (0.96.93)
LEAD = 0.05                      # the mouth starts moving this early, the way a real one does before the sound
ATTACK, RELEASE = 0.045, 0.085   # seconds to open towards a shape, and to let go of it (letting go is slower, so shapes blend)
SOFT = 0.8                       # t, d, n, s, l...: the tongue does the work, so the lips only part a little (the "eh" picture, a little weaker)
MIN_HOLD = 0.04                  # a sound shorter than this does not get its own mouth shape (the one before carries on)
GAP_HOLD = 0.12                  # a pause shorter than this between two sounds keeps the mouth where it was instead of closing it
JAW = {"ah": 1.0, "oh": 0.7, "eh": 0.45, "ee": 0.35, "oo": 0.5, "fv": 0.15}   # how far the chin drops for each mouth picture
NOD = 0.007                      # her head dips this fraction of her height on an open mouth (a speaking nod)
SWAY = 0.0035                    # and drifts this fraction of her width from side to side while she talks
TALK_IDLE = 0.0                  # how much of the flip book keeps playing while she talks (0 = none)
SALUTE_LINE = re.compile(r"(?<![a-z0-9])(?:o7|oh seven)(?![a-z0-9])", re.IGNORECASE)      # a line she says that contains o7
SALUTE_REPEAT = 8.0              # a second salute request within this many seconds of one starting is ignored

# ---- pose clips (0.96.93): short recorded moments she plays at the right time ----
CLIP_IN, CLIP_OUT, CLIP_OUT_FAST = 0.35, 0.5, 0.2      # seconds to fade a clip in, out, and out when she starts to talk
BORED_AFTER = (90.0, 180.0)      # quiet for this long (a random time in this range) and she may get bored
POSE_GAP = 60.0                  # at least this long between two clips
PLEASED_CHANCE = 0.25            # how often a spoken line ends with the pleased clip
CLIP_LRU = 1                     # clips other than thinking and listening that are kept in memory
# ---- little gestures made from her one picture (no video needed) and the game events that trigger them ----
GESTURES = {"nod": 1.0, "shake": 1.2, "tilt": 2.4, "glance_left": 2.0, "glance_right": 2.0, "startle": 0.9}      # name -> seconds
GESTURE_GAP = 3.0                # a gesture does not start within this many seconds of the last one (a startle always may)
REACT_GAP, STARTLE_GAP = 8.0, 5.0       # the least time between two reactions to game events
REACTIONS = {                    # game event -> (what she does, how likely)
    "DockingGranted": ("nod", 0.7), "DockingDenied": ("shake", 0.9),
    "MissionAccepted": ("nod", 0.5), "MissionCompleted": ("pleased", 0.7), "MissionFailed": ("shake", 0.8), "MissionAbandoned": ("shake", 0.4),
    "RedeemVoucher": ("pleased", 0.3), "SellExplorationData": ("pleased", 0.3), "MultiSellExplorationData": ("pleased", 0.4), "SellOrganicData": ("pleased", 0.3),
    "EscapeInterdiction": ("pleased", 0.6), "FSSAllBodiesFound": ("pleased", 0.8), "UndiscoveredSystem": ("pleased", 0.5), "GameMilestone": ("pleased", 0.8),
    "UniqueBio": ("tilt", 0.5), "CodexEntry": ("tilt", 0.4), "FSSSignalDiscovered": ("tilt", 0.3), "SAASignalsFound": ("tilt", 0.4),
    "WingJoined": ("nod", 0.6), "WingInvite": ("nod", 0.6), "WingAdd": ("nod", 0.4), "WingLeft": ("tilt", 0.4),
    "ReceiveText": ("glance", 0.3),
    "Interdicted": ("startle", 0.9), "UnderAttack": ("startle", 0.5), "HullDamage": ("startle", 0.5), "HeatDamage": ("startle", 0.5),
    "CockpitBreached": ("startle", 1.0), "InDanger": ("startle", 0.6), "SelfDestruct": ("startle", 1.0), "Died": ("startle", 1.0), "FuelPanic": ("startle", 0.8),
    "Synthesis": ("nod", 0.6),
    "Shutdown": ("salute", 1.0),
}
JAW_DROP = 0.006                 # the biggest chin drop, as a fraction of her height
JAW_TOP, JAW_FULL, JAW_CHIN, JAW_END = 0.338, 0.372, 0.42, 0.462     # where the jaw moves, as fractions of the picture height: upper lip, full, chin, back to still


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


# The sounds Kokoro hands over (its phoneme letters) and which mouth picture each one needs.
PHONEME_SHAPES = {}
for _letters, _shape in (("aɑæʌɐIW", "ah"), ("eɛəɜɚᵻA", "eh"), ("iɪy", "ee"), ("oɔɒOQY", "oh"), ("uʊwɯ", "oo"),
                         ("pbm", "pressed"), ("fv", "fv"), ("tdsznlʃʒʧʤθð", "soft")):
    for _char in _letters:
        PHONEME_SHAPES[_char] = _shape
NO_TIME = "ˈˌː"                 # stress and length marks: they carry no mouth shape of their own


def track_from_phonemes(items):
    """items = [(phoneme letter, seconds), ...] -> a mouth track [(start, end, picture or None)] with the real timing of each sound."""
    track, t = [], 0.0
    for char, seconds in items:
        seconds = max(0.0, float(seconds))
        if char in NO_TIME and track:
            start, end, shape = track[-1]
            track[-1] = (start, end + seconds, shape)             # a stress mark just lengthens the sound before it
        else:
            track.append((t, t + seconds, PHONEME_SHAPES.get(char)))
        t += seconds
    return track


def track_from_timeline(entries, cps=DEFAULT_CPS):
    """entries = [(seconds, text or None, phonemes or None), ...] one per piece of sound actually played (beats and pauses included).
    Pieces that know their phonemes use the exact timing; others (older cached sounds) use the letters of their text squeezed to fit."""
    track, offset = [], 0.0
    for seconds, text, phonemes in entries:
        seconds = max(0.0, float(seconds))
        if phonemes:
            part = track_from_phonemes(phonemes)
        elif text:
            part = build_track(text, cps)
        else:
            part = []
        length = track_length(part)
        stretch = seconds / length if (length > 0 and seconds > 0) else 1.0
        for start, end, shape in part:
            track.append((offset + start * stretch, offset + end * stretch, shape))
        offset += seconds
        if not part and seconds > 0:
            track.append((offset - seconds, offset, None))
    return track


def track_length(track):
    return track[-1][1] if track else 0.0


def shape_at(track, elapsed):
    for start, end, shape in track:
        if start <= elapsed < end:
            return shape
    return None


def mouth_at(track, elapsed):
    """Like shape_at, but kinder to the eye: a very short sound lends its time to the one before, and a short pause between two sounds
    keeps the mouth where it was (a real mouth does not shut between every word)."""
    for k, (start, end, shape) in enumerate(track):
        if start <= elapsed < end:
            if shape is None:
                if end - start < GAP_HOLD and 0 < k < len(track) - 1 and track[k - 1][2] and track[k + 1][2]:
                    return track[k - 1][2]
                return None
            if end - start < MIN_HOLD and shape != "pressed" and k > 0 and track[k - 1][2]:
                return track[k - 1][2]
            return shape
    return None


def targets(mouth):
    """Which mouth pictures to show, and how strongly, for a shape name. 'soft' is the eh picture, half open."""
    if mouth == "soft":
        return {"eh": SOFT}
    return {mouth: 1.0} if mouth else {}


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
        self.pad_left = self.pad_right = 0                # room beside her for a clip's arm (the salute): the window is this much wider
        self.wide_clips = set()
        try:
            clips_meta = json.loads((directory / "clips.json").read_text(encoding="utf-8"))
            pad = clips_meta.get("pad")
            if pad and len(pad) == 2:
                self.pad_left, self.pad_right = int(round(float(pad[0]) * self.width)), int(round(float(pad[1]) * self.width))
            self.wide_clips = {k for k, v in clips_meta.items() if isinstance(v, dict) and v.get("wide")}
        except Exception:
            pass
        self.window_w = self.width + self.pad_left + self.pad_right
        self.window_h = self.height + PAD_TOP + PAD_BOTTOM
        self.directory = directory
        self._idle = None
        self.rings = self._rings()
        self.clips = clip_names(directory)
        self.clip_rates = {n: clip_fps(directory, n) for n in self.clips}

    @property
    def idle(self):
        """(frames, shifts, fps) of the flip book; loaded the first time it is needed."""
        if self._idle is None:
            self._idle = load_idle(self.directory, self.height, self.width)
        return self._idle

    def _rings(self):
        """The two glowing rings she stands on, as a 0..1 strength per pixel in window coordinates."""
        from PIL import Image, ImageDraw
        layer = Image.new("L", (self.window_w, self.window_h), 0)
        draw = ImageDraw.Draw(layer)
        cx, cy = self.pad_left + self.width // 2, PAD_TOP + self.height + 14
        for fraction, level in ((0.46, 235), (0.32, 140)):
            rx = int(self.width * fraction)
            ry = max(3, int(rx * 0.2))
            draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), outline=level, width=2)
        return np.asarray(layer, dtype=np.float32)[..., None] / 255.0


_IDLE_CACHE = {}


def load_idle(directory, height, width):
    """The flip book (see tools/make_flipbook.py): (frames as uint8 arrays at her size, head shifts in pixels at her size, frames per second).
    Empty when the pictures are not there. Cached, because loading takes a moment."""
    key = (str(directory), int(height))
    if key in _IDLE_CACHE:
        return _IDLE_CACHE[key]
    result = ([], [], 30.0)
    try:
        from PIL import Image
        directory = Path(directory)
        meta = json.loads((directory / "idle.json").read_text(encoding="utf-8"))
        scale = height / float(meta["size"][1])
        frames = []
        for number in range(int(meta["frames"])):
            picture = Image.open(directory / "idle" / ("%03d.jpg" % number)).convert("RGB").resize((width, height), Image.BILINEAR)
            frames.append(np.asarray(picture, dtype=np.uint8))
        shifts = [(dx * scale, dy * scale) for dx, dy in meta["shifts"]]
        result = (frames, shifts, float(meta.get("fps", 30)))
    except Exception:
        result = ([], [], 30.0)
    _IDLE_CACHE[key] = result
    return result


_CLIPS = {}                       # (folder, height, name) -> frames, loaded once
_CLIP_ORDER = []
_CLIP_LOADING = set()
_CLIP_LOCK = threading.Lock()
PINNED = ("thinking", "listening")


def load_clip(directory, name, height, width, pad_left=0, pad_right=0, wide=False):
    """The pictures of one pose clip at her size (uint8 arrays), or [] when it is missing. A 'wide' clip also has room beside her (for an arm)."""
    try:
        from PIL import Image
        directory = Path(directory)
        meta = json.loads((directory / "clips.json").read_text(encoding="utf-8"))[name]
        frames = []
        for number in range(int(meta["frames"])):
            picture = Image.open(directory / "clips" / name / ("%03d.jpg" % number)).convert("RGB").resize(
                (width + pad_left + pad_right if wide else width, height), Image.BILINEAR)
            frames.append(np.asarray(picture, dtype=np.uint8))
        return frames
    except Exception:
        return []


def clip_names(directory):
    try:
        meta = json.loads((Path(directory) / "clips.json").read_text(encoding="utf-8"))
        return [k for k, v in meta.items() if isinstance(v, dict) and (Path(directory) / "clips" / k).is_dir()]
    except Exception:
        return []


def clip_fps(directory, name):
    try:
        return float(json.loads((Path(directory) / "clips.json").read_text(encoding="utf-8"))[name].get("fps", 12))
    except Exception:
        return 12.0


def get_clip(assets, name, wait=False):
    """The frames of a clip if they are in memory; otherwise start loading them in the background (so the screen never stops) and return None.
    Only thinking and listening stay in memory for good; of the others the latest one is kept."""
    key = (str(assets.directory), assets.height, name)
    with _CLIP_LOCK:
        if key in _CLIPS:
            if name not in PINNED:
                _CLIP_ORDER.remove(key)
                _CLIP_ORDER.append(key)
            return _CLIPS[key]
        if key in _CLIP_LOADING and not wait:
            return None
        _CLIP_LOADING.add(key)

    def work():
        frames = load_clip(assets.directory, name, assets.height, assets.width, assets.pad_left, assets.pad_right, name in assets.wide_clips)
        with _CLIP_LOCK:
            _CLIP_LOADING.discard(key)
            if frames:
                _CLIPS[key] = frames
                if name not in PINNED:
                    _CLIP_ORDER.append(key)
                    while len(_CLIP_ORDER) > CLIP_LRU:
                        _CLIPS.pop(_CLIP_ORDER.pop(0), None)
        return frames

    if wait:
        return work() or None
    threading.Thread(target=work, daemon=True, name="hologram-clip").start()
    return None


def clear_clips():
    with _CLIP_LOCK:
        _CLIPS.clear()
        _CLIP_ORDER.clear()
        _CLIP_LOADING.clear()


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
        self.levels = []              # (time, loudness) of the real sound, 40 per second while she talks
        self.level_ref = 0.05         # what 'loud' means for this voice (adapts)
        self.level_open = 1.0         # 0 = the sound is quiet or a pause, 1 = loud
        self.levels_live = False
        self.time_scale = 1.0         # stretches the mouth track so it ends when the real sound ends
        self.block = None             # the latest piece of sound handed to the speakers: (seconds played before it, when, length)
        self.stalled = False          # the voice is still making the next piece: nothing is playing, so the lips wait
        self.exact_track = False      # True once the voice has told us the exact timing of every sound
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
        self.idle_on = True           # play the flip book (breathing, sway) while she is quiet
        self.idle_mix = 1.0           # 1 = the flip book, 0 = the still picture that the mouth pictures fit
        self.talk_motion = True       # her head nods and sways a little while she talks
        self.talk_idle = TALK_IDLE
        self.poses_on = True          # play the recorded pose clips (thinking, listening, pleased, bored)
        self.clip = None              # the name of the clip playing, or None
        self.clip_frames, self.clip_fps = None, 12.0
        self.clip_forced = False      # the test button started it: it plays to the end whatever she is doing
        self.clip_start = 0.0
        self.clip_mix = 0.0           # 0..1, how much of the clip shows
        self.clip_fast_out = False
        self.last_activity = clock()
        self.bored_after = 0.0        # filled in by _rest(): how long she may be quiet before she gets bored
        self.next_pose = 0.0          # no clip starts before this
        self.thinking_done = self.listening_done = False     # this round of thinking or listening already got its clip
        self.pose_wanted = None       # (clip name, earliest time) waiting for a calm moment
        self.bored_pick = None
        self.g_name, self.g_start, self.g_last = None, 0.0, -1e9     # the little gesture she is making (nod, shake...)
        self.react_last = -1e9
        self.salute_at = None         # when a salute was asked for (o7, or the game just loaded), and when to give up on it
        self.salute_expire = 0.0
        self.salute_voice = False     # the salute goes with a line she is saying, so it plays while she talks
        self.last_salute = -1e9
        self._rest(clock())
        self.talk_presence = 0.0      # 0..1, fades in while she talks (the side-to-side drift follows it)
        self.nod = 0.0                # 0..1, how far the head has dipped (smoothed from how open her mouth is)

    # ---- what happens ----
    def speech_started(self, text, now=None):
        now = self.clock() if now is None else now
        self.line_text = str(text or "")
        if SALUTE_LINE.search(self.line_text):
            self.salute(now, with_speech=True)                     # she says o7, so she salutes while she says it
        self._rest(now)
        self.track = build_track(self.line_text, self.cps)
        self.track_start, self.speaking = now, True
        self.time_scale = 1.0
        self.exact_track = False
        self.block = None
        self.stalled = False

    def add_levels(self, taken, now=None):
        """taken = [(time, [four loudness numbers]), ...] from the speech manager: each group is 100 ms of sound."""
        for entry in taken:
            stamp, values = entry[0], entry[1]
            if len(entry) >= 4 and entry[2] is not None:
                self.block = (float(entry[2]), float(stamp), float(entry[3]))      # (seconds of sound played before this block, when, its length)
            for k, value in enumerate(values):
                self.levels.append((stamp + k * (0.1 / max(1, len(values))), float(value)))
        del self.levels[:-120]

    def _level_now(self, now):
        """The loudness of the sound playing right now (0 to 1 of this voice's usual loud), or None when we have no fresh numbers."""
        while len(self.levels) > 1 and self.levels[1][0] <= now:
            self.levels.pop(0)
        if not self.levels or self.levels[0][0] > now + 0.05 or now - self.levels[0][0] > 0.4:
            return None
        value = self.levels[0][1]
        self.level_ref = max(0.02, self.level_ref * 0.9995, value)
        return max(0.0, min(1.0, value / self.level_ref))

    def set_timeline(self, entries):
        """The voice has told us exactly what it played, piece by piece: replace the guessed mouth track with the real one."""
        track = track_from_timeline(entries, self.cps)
        if track:
            self.track = track
            self.time_scale = 1.0
            self.exact_track = True

    def set_duration(self, seconds):
        """The real length of the sound is known: stretch or squeeze the mouth so it finishes exactly when she does."""
        length = track_length(self.track)
        if self.exact_track:
            return                                            # the exact timing needs no stretching
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
        self._rest(now)
        if letters >= 25 and self.rng.random() < PLEASED_CHANCE:
            self.pose_wanted = ("pleased", now + SMILE_SECONDS)             # after the smile, so the two do not fight

    def heard_her_name(self, now=None):
        """Her name was said on its own: she is waiting for the rest."""
        now = self.clock() if now is None else now
        self.listen_until = now + LISTEN_SECONDS
        self._rest(now)

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
        talking = self.speaking or now < self.smile_until or any(self.weights.get(n, 0.0) > 0.05 for n in LIVE_SHAPES)
        self._gesture_values(now)                                  # lets a finished gesture expire even when nothing is being drawn
        self._poses(listening, thinking, now, dt)
        goal_idle = 0.0 if self.clip else ((self.talk_idle if talking else 1.0) if self.idle_on else 0.0)
        rate = 0.3 if goal_idle < self.idle_mix else 0.9                                # leaves the loop fast, returns to it slowly
        self.idle_mix += max(-1.0, min(1.0, (goal_idle - self.idle_mix) / max(0.05, rate) * dt))
        self.idle_mix = max(0.0, min(1.0, self.idle_mix))
        level = self._level_now(now) if self.speaking else None
        self.levels_live = level is not None
        if level is not None:
            goal = 0.0 if level < 0.10 else min(1.0, (level - 0.10) / 0.45)             # a pause or a quiet bit closes the mouth
            self.level_open += (goal - self.level_open) * min(1.0, dt / 0.04)
        else:
            self.level_open = 1.0
        mouth = self._mouth_goal(now)
        if self.levels_live and self.level_open < 0.12:
            mouth = None
        wanted_mouth = targets(mouth)
        for name in self.weights:
            if name == "eyes":
                goal = 1.0 if now < self.blink_until else 0.0
                speed = 0.035
            else:
                goal = wanted_mouth.get(name, 0.0)
                speed = ATTACK if goal > self.weights[name] else RELEASE
            self.weights[name] += (goal - self.weights[name]) * min(1.0, dt / speed)
        openness = min(1.0, sum(min(1.0, w) * JAW.get(name, 0.0) for name, w in self.weights.items()))
        self.nod += (openness - self.nod) * min(1.0, dt / 0.12)
        self.talk_presence += ((1.0 if talking else 0.0) - self.talk_presence) * min(1.0, dt / 0.4)
        if now >= self.blink_at:
            self.blink_until = now + 0.15
            self.blink_at = now + 2.4 + self.rng.random() * 3.2
        if self.flicker_on and now >= self.next_glitch:
            self.glitch_until = now + 0.14
            self.next_glitch = now + 2.8 + self.rng.random() * 3.2
            self.strips = [(self.rng.randint(0, max(1, self.assets.window_h - 20)), self.rng.randint(4, 22),
                            self.rng.randint(-8, 8)) for _ in range(5)]
        return self.power

    def _elapsed(self, now):
        """How far into the line the SOUND is. By the clock while we have no word from the speakers; otherwise by how much sound they
        have really been given, so when the voice stalls (a long answer is still being made) the lips stop instead of running ahead."""
        self.stalled = False
        if self.block is None:
            return now - self.track_start
        before, stamp, length = self.block
        age = now - stamp
        if age > length + 0.3:
            self.stalled = True
            return before + length
        return before + max(0.0, min(age, length))

    # ---- little gestures and reactions ----
    def gesture(self, name, now=None):
        """Make a small movement from her one picture: nod, shake, tilt, glance_left, glance_right, startle. False if she is busy or it is too soon."""
        now = self.clock() if now is None else now
        if name not in GESTURES or not self.poses_on or self.clip or self.moving or self.power < 0.9:
            return False
        if self.g_name and name != "startle":
            return False
        if name != "startle" and now - self.g_last < GESTURE_GAP:
            return False
        self.g_name, self.g_start = name, now
        return True

    def react_to(self, event_name, now=None):
        """A game event happened: maybe she reacts (a nod, a shake of the head, a startle, a pleased clip...). Returns True if she did."""
        now = self.clock() if now is None else now
        item = REACTIONS.get(event_name)
        if not item or not self.poses_on:
            return False
        kind, chance = item
        if self.rng.random() > chance:
            return False
        if now - self.react_last < (STARTLE_GAP if kind == "startle" else REACT_GAP):
            return False
        if kind == "glance":
            kind = self.rng.choice(("glance_left", "glance_right"))
        if kind in GESTURES:
            done = self.gesture(kind, now)
        elif kind == "salute":
            self.salute(now)
            done = True
        else:                                                         # a clip, played when she has a calm moment
            done = self.pose_wanted is None and kind in self.assets.clips
            if done:
                self.pose_wanted = (kind, now)
        if done:
            self.react_last = now
        return done

    def _gesture_values(self, now):
        """(sideways, up/down as fractions of her size, turn -1..1, lean, flash) for the gesture in progress; all zero when there is none."""
        if not self.g_name:
            return 0.0, 0.0, 0.0, 0.0, 0.0
        t, d = now - self.g_start, GESTURES[self.g_name]
        if t >= d:
            self.g_name, self.g_last = None, now
            return 0.0, 0.0, 0.0, 0.0, 0.0
        edge = min(1.0, max(0.0, min(t / 0.12, (d - t) / 0.12)))
        hump = math.sin(math.pi * t / d)
        if self.g_name == "nod":
            return 0.0, 0.02 * (1.0 - math.cos(4.0 * math.pi * t / d)) / 2.0 * edge, 0.0, 0.0, 0.0
        if self.g_name == "shake":
            return 0.0, 0.0, 1.5 * math.sin(2.0 * math.pi * t / 0.6) * edge, 0.0, 0.0
        if self.g_name == "tilt":
            return 0.0, 0.004 * hump, 0.0, 0.10 * hump ** 0.6, 0.0
        if self.g_name in ("glance_left", "glance_right"):
            side = -1.0 if self.g_name == "glance_left" else 1.0
            return 0.0, 0.0, side * 1.3 * min(1.0, 2.2 * hump), 0.0, 0.0
        if self.g_name == "startle":
            return 0.0, -0.014 * math.exp(-t / 0.1) * (1.0 - math.exp(-t / 0.02)), 0.0, 0.0, 0.7 * math.exp(-t / 0.2)
        return 0.0, 0.0, 0.0, 0.0, 0.0

    def _shift(self, frame, dx, dy):
        """The whole picture moved by (dx, dy) pixels (smoothly up and down); the edges repeat."""
        h, w = frame.shape[:2]
        ys = np.clip(np.arange(h, dtype=np.float32) - dy, 0, h - 1.001)
        i0 = np.floor(ys).astype(np.int32)
        frac = (ys - i0)[:, None, None]
        out = frame[i0] * (1.0 - frac) + frame[i0 + 1] * frac
        shift = int(round(dx))
        if shift:
            out = np.roll(out, shift, axis=1)
            if shift > 0:
                out[:, :shift] = out[:, shift:shift + 1]
            else:
                out[:, shift:] = out[:, shift - 1:shift]
        return out

    def _lean(self, frame, k):
        """Tip her head to one side: from the neck up each row slides sideways, more the higher it is (k = how far, 0.07 is a clear tilt)."""
        a = self.assets
        h, w = frame.shape[:2]
        neck = JAW_END * a.height
        ys = np.arange(h, dtype=np.float32)
        slide = np.where(ys < neck, (neck - ys) * k, 0.0)[:, None]
        cols = np.arange(w, dtype=np.float32)[None, :] - slide
        left = np.clip(np.floor(cols).astype(np.int32), 0, w - 1)
        right = np.clip(left + 1, 0, w - 1)
        frac = (cols - np.floor(cols))[..., None]
        rows = np.arange(h)[:, None]
        return frame[rows, left] * (1.0 - frac) + frame[rows, right] * frac

    # ---- pose clips ----
    def _rest(self, now):
        """She did or heard something: the 'quiet for a long time' clock starts again."""
        self.last_activity = now
        self.bored_after = self.rng.uniform(*BORED_AFTER)

    def start_clip(self, name, now, forced=False):
        """Begin a pose clip if its pictures are ready (they load in the background; if not, she simply skips it this time)."""
        a = self.assets
        if name not in a.clips:
            return False
        frames = get_clip(a, name)
        if not frames:
            return False
        self.clip, self.clip_start, self.clip_fast_out, self.clip_forced = name, now, False, forced
        self.g_name = None
        self.clip_frames, self.clip_fps = frames, a.clip_rates.get(name, 12.0)
        self.next_pose = now + POSE_GAP
        if name == "salute":
            self.last_salute = now
        return True

    def salute(self, now=None, delay=0.0, with_speech=False):
        """She should salute as soon as it is calm (you said o7, or the game just loaded). It waits for her to stop talking, and is dropped after 8 seconds.
        with_speech: she is SAYING o7 right now (a chat reply, say), so the salute starts at once and plays while she talks."""
        now = self.clock() if now is None else now
        if now - self.last_salute < SALUTE_REPEAT:
            return                                                    # one is already on its way or has just played
        if self.poses_on and "salute" in self.assets.clips:
            self.salute_at, self.salute_expire = now + delay, now + delay + 8.0
            self.salute_voice = bool(with_speech)
            get_clip(self.assets, "salute")                                          # start loading it now

    def stop_clip(self, fast=False):
        self.clip = None
        self.clip_fast_out = fast

    def preload_clips(self):
        """Start loading thinking and listening (the ones that must be ready at once); call it a few seconds after she appears."""
        for name in PINNED:
            if name in self.assets.clips:
                get_clip(self.assets, name)

    def _poses(self, listening, thinking, now, dt):
        """Decide which clip should play, and fade it in or out."""
        if not self.poses_on and not self.clip_forced:
            if self.clip:
                self.stop_clip(fast=True)
        elif self.clip_forced and self.clip:
            if now - self.clip_start > len(self.clip_frames) / max(1.0, self.clip_fps):
                self.stop_clip()
                self.clip_forced = False
        else:
            calm = (not self.speaking) and self.power > 0.9 and not self.moving
            if self.salute_at is not None and self.salute_voice and self.power > 0.9 and not self.moving and now >= self.salute_at:
                if self.clip is None or self.clip != "salute":
                    if self.clip:
                        self.stop_clip(fast=True)
                    if self.start_clip("salute", now):
                        self.salute_at = None
                        self.salute_voice = False
            if self.salute_at is not None and now > self.salute_expire:
                self.salute_at = None                                                # she never got a calm moment: forget it
            if self.speaking and self.clip and self.clip != "salute":
                self.stop_clip(fast=True)
            listen_now = bool(listening) or now < self.listen_until
            if calm:
                if self.salute_at is not None and now >= self.salute_at:
                    if now > self.salute_expire:
                        self.salute_at = None
                    elif self.clip is None and not thinking and self.start_clip("salute", now):
                        self.salute_at = None
                elif thinking and self.clip is None and not self.thinking_done:
                    self.thinking_done = self.start_clip("thinking", now)           # if it is still loading we try again on the next tick
                elif listen_now and not thinking and self.clip is None and not self.listening_done:
                    self.listening_done = self.start_clip("listening", now)
                elif self.clip is None and now >= self.next_pose and not thinking and not listen_now:
                    if self.pose_wanted and now >= self.pose_wanted[1]:
                        if now > self.pose_wanted[1] + 10.0 or self.start_clip(self.pose_wanted[0], now):
                            self.pose_wanted = None                                 # started, or it took too long to load: forget it
                    elif now - self.last_activity >= self.bored_after:
                        names = [n for n in ("bored1", "bored2") if n in self.assets.clips]
                        if names:
                            if self.bored_pick not in names:
                                self.bored_pick = self.rng.choice(names)             # pick once, so we wait for this one to load
                            if self.start_clip(self.bored_pick, now):
                                self.bored_pick = None
                                self._rest(now)
                        else:
                            self._rest(now)
            if self.clip == "thinking" and not thinking:
                self.stop_clip()                                                    # the answer is coming
            elif self.clip == "listening" and not listen_now:
                self.stop_clip()
            elif self.clip and now - self.clip_start > len(self.clip_frames) / max(1.0, self.clip_fps):
                self.stop_clip()                                                    # the clip is over: back to the loop
        if thinking or listening or self.speaking:
            self.last_activity = now
        if not thinking:
            self.thinking_done = False
        if not (bool(listening) or now < self.listen_until):
            self.listening_done = False
        goal = 1.0 if self.clip else 0.0
        seconds = CLIP_IN if goal > self.clip_mix else (CLIP_OUT_FAST if self.clip_fast_out else CLIP_OUT)
        self.clip_mix += max(-dt / seconds, min(dt / seconds, goal - self.clip_mix))
        if self.clip_mix <= 0.0 and not self.clip:
            self.clip_frames = None

    def _clip_picture(self, now):
        """The clip's picture for this moment (two neighbouring frames blended), or None."""
        frames = getattr(self, "clip_frames", None)
        if not frames or self.clip_mix <= 0.01:
            return None
        position = max(0.0, (now - self.clip_start) * self.clip_fps)
        last = len(frames) - 1
        i0 = min(last, int(position))
        i1 = min(last, i0 + 1)
        frac = position - int(position) if i0 < last else 0.0
        if frac < 0.02:
            return frames[i0].astype(np.float32)
        return frames[i0].astype(np.float32) * (1.0 - frac) + frames[i1].astype(np.float32) * frac

    def _mouth_goal(self, now):
        if self.speaking:
            elapsed = self._elapsed(now) / self.time_scale
            if self.stalled:
                return None
            if elapsed > track_length(self.track) + 0.4:
                return None
            return mouth_at(self.track, elapsed + LEAD)
        if now < self.smile_until:
            return "smile"
        return None

    def _jaw_drop(self):
        """How far her chin is down right now, in pixels (0 when her mouth is closed)."""
        amount = sum(min(1.0, w) * JAW.get(name, 0.0) for name, w in self.weights.items())
        return min(1.0, amount) * JAW_DROP * self.assets.height

    def _nod_offsets(self, now, amount):
        """(sideways, up/down) in pixels: her head dips a little with each open syllable and drifts slowly from side to side while she talks.
        `amount` is how much of the effect to show (it fades in and out with the flip book)."""
        a = self.assets
        dy = self.nod * NOD * a.height * amount
        dx = math.sin(now * 1.3) * SWAY * a.width * amount * self.talk_presence
        return dx, dy

    def _nod(self, frame, now, amount):
        dx, dy = self._nod_offsets(now, amount)
        if abs(dy) < 0.05 and abs(dx) < 0.05:
            return frame
        return self._shift(frame, dx, dy)

    def _drop_jaw(self, frame, drop, shift_y=0):
        """Slide the lower face down by `drop` pixels, most at the chin and fading to nothing at the lips above and the neck below,
        so the mouth picture looks fixed to a face that moves instead of a sticker on a still one."""
        h = frame.shape[0]
        top, full, chin, end = [int(round(f * self.assets.height)) + shift_y for f in (JAW_TOP, JAW_FULL, JAW_CHIN, JAW_END)]
        top, end = max(1, top), min(h - 2, end)
        if end <= top + 2:
            return frame
        ys = np.arange(top, end + 1, dtype=np.float32)
        ramp = np.interp(ys, [top, full, chin, end], [0.0, 1.0, 1.0, 0.0])
        src = np.clip(ys - drop * ramp, 0, h - 2)
        i0 = np.floor(src).astype(np.int32)
        frac = (src - i0)[:, None, None]
        out = frame.copy()
        out[top:end + 1] = frame[i0] * (1.0 - frac) + frame[i0 + 1] * frac
        return out

    # ---- the pixels ----
    def render(self, now=None):
        """The picture as an (h, w, 3) uint8 array in window size. See-through pixels are exactly KEY."""
        now = self.clock() if now is None else now
        a = self.assets
        frame = a.base.copy()
        shift_x = shift_y = 0
        frames, shifts, fps = a.idle if (self.idle_on and self.idle_mix > 0.01) else ([], [], 30.0)
        if frames:
            position = now * fps
            i0 = int(position) % len(frames)
            i1 = (i0 + 1) % len(frames)
            frac = position - int(position)
            moving_frame = frames[i0].astype(np.float32) * (1.0 - frac) + frames[i1].astype(np.float32) * frac
            frame = frame * (1.0 - self.idle_mix) + moving_frame * self.idle_mix
            sx = shifts[i0][0] * (1.0 - frac) + shifts[i1][0] * frac
            sy = shifts[i0][1] * (1.0 - frac) + shifts[i1][1] * frac
            shift_x, shift_y = int(round(sx * self.idle_mix)), int(round(sy * self.idle_mix))   # the mouth and eye pictures follow her head
        picture = self._clip_picture(now)
        margins = None
        if picture is not None:
            if picture.shape[1] > a.width:                                              # a wide clip: the middle is her picture, the sides are her arm
                margins = (picture[:, :a.pad_left] * self.clip_mix, picture[:, a.pad_left + a.width:] * self.clip_mix)
                picture = picture[:, a.pad_left:a.pad_left + a.width]
            frame = frame * (1.0 - self.clip_mix) + picture * self.clip_mix
            shift_x = shift_y = 0
        for name, weight in self.weights.items():
            if weight < 0.02 or name not in a.sprites:
                continue
            x, y, rgb, alpha = a.sprites[name]
            x, y = x + shift_x, y + shift_y
            if x < 0 or y < 0:
                continue
            strength = min(1.0, weight) * (reach(self.open_fraction, name) if name != "eyes" else 1.0) * (1.0 - (0.0 if self.clip == "salute" else self.clip_mix))   # a clip has its own face (the salute keeps her head still, so her lips stay on it)
            if name in LIVE_SHAPES and self.levels_live:
                strength *= 0.35 + 0.65 * self.level_open                                  # follow the real loudness
            h, w = rgb.shape[:2]
            region = frame[y:y + h, x:x + w]
            rh, rw = region.shape[:2]
            if rh <= 0 or rw <= 0:
                continue
            blend = alpha[:rh, :rw] * strength
            region[:] = region * (1.0 - blend) + rgb[:rh, :rw] * blend
        drop = self._jaw_drop()
        if drop > 0.05:
            frame = self._drop_jaw(frame, drop, shift_y)
        move_x = move_y = 0.0
        if self.talk_motion and self.idle_mix < 0.99 and (self.nod > 0.01 or self.talk_presence > 0.02):
            move_x, move_y = self._nod_offsets(now, 1.0 - self.idle_mix)
        g_x, g_y, g_turn, g_lean, g_flash = self._gesture_values(now)
        move_x += g_x * a.width
        move_y += g_y * a.height
        if not self.fx_turn and g_turn:
            move_x += g_turn * a.width * 0.03                                           # no fake 3D turn: a sideways nudge instead
        if abs(move_x) > 0.05 or abs(move_y) > 0.05:
            frame = self._shift(frame, move_x, move_y)
        if g_lean:
            frame = self._lean(frame, g_lean)
        if self.fx_turn:
            if g_turn:
                frame = self._turn(frame, now, swing=max(-1.8, min(1.8, self.turn_angle(now) * 0.4 + g_turn)), damp=False)
            else:
                frame = self._turn(frame, now)
        if g_flash > 0.01:
            frame = frame * (1.0 + g_flash)
        # a slow breathing flicker, and a rougher one while she powers up or down
        level = self.power
        if self.flicker_on:
            level *= 0.95 + 0.05 * math.sin(now * 23.0) * math.sin(now * 7.3)
            if 0.02 < self.power < 0.98:
                level *= 0.55 + 0.45 * self.rng.random()
        level = max(0.0, min(1.0, level))
        tint = tint_matrix(self.mix).T
        sweep = int((now * 70.0) % (a.height * 1.6)) - int(a.height * 0.2)

        def finish(piece):
            """Scan lines, the bright sweep, the flicker and the colour: the same for her picture and for the sides of a wide clip."""
            piece[::3] *= 0.84
            lo, hi = max(0, sweep - 7), min(a.height, sweep + 7)
            if hi > lo:
                piece[lo:hi] *= 1.0 + 0.25 * np.hanning(hi - lo + 2)[1:-1, None, None]
            piece *= level
            piece = piece @ tint
            np.clip(piece, 0, 255, out=piece)
            return piece

        frame = finish(frame)
        # into the window: padded, floating up and down a pixel or two, with her rings under her
        bob = int(round(math.sin(now * 1.3) * 2.0)) if self.flicker_on else 0
        out = np.zeros((a.window_h, a.window_w, 3), dtype=np.float32)
        top = PAD_TOP + bob
        out[top:top + a.height, a.pad_left:a.pad_left + a.width] = frame
        if margins is not None and self.clip_mix > 0.01:
            if margins[0].shape[1]:
                out[top:top + a.height, :a.pad_left] = finish(np.array(margins[0], dtype=np.float32))
            if margins[1].shape[1]:
                out[top:top + a.height, a.pad_left + a.width:] = finish(np.array(margins[1], dtype=np.float32))
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
        """A rough 'how close to you' map (0 = far, 1 = near), made once: a head with a nose, hair behind it, a neck, shoulders and a rounded chest.
        It is built from simple rounded shapes plus a little of the picture's own brightness, so lit parts (nose, cheeks, collar) stand out."""
        a = self.assets
        if getattr(self, "_depth", None) is None or self._depth.shape != (a.height, a.width):
            from PIL import Image, ImageFilter
            ys, xs = np.mgrid[0:a.height, 0:a.width].astype(np.float32)
            w, hgt = float(a.width), float(a.height)

            def dome(cx, cy, rx, ry, top, bottom=0.0):
                """A rounded hill: `top` in the middle, falling to `bottom` at the edge, 0 outside."""
                d = ((xs - cx * w) / (rx * w)) ** 2 + ((ys - cy * hgt) / (ry * hgt)) ** 2
                return np.where(d < 1.0, bottom + (top - bottom) * np.sqrt(np.clip(1.0 - d, 0.0, 1.0)), 0.0)

            parts = [
                dome(0.50, 0.38, 0.50, 0.46, 0.38, 0.12),             # hair: big and far back
                dome(0.50, 0.46, 0.09, 0.14, 0.50, 0.30),             # neck
                dome(0.50, 0.26, 0.15, 0.17, 0.82, 0.55),             # face: a rounded head
                dome(0.50, 0.30, 0.035, 0.05, 1.00, 0.80),            # nose sticks out
                dome(0.43, 0.25, 0.04, 0.03, 0.88, 0.70),             # cheeks and brow
                dome(0.57, 0.25, 0.04, 0.03, 0.88, 0.70),
                dome(0.50, 0.80, 0.50, 0.26, 0.66, 0.35),             # shoulders and body
                dome(0.41, 0.70, 0.12, 0.10, 0.78, 0.62),             # chest
                dome(0.59, 0.70, 0.12, 0.10, 0.78, 0.62),
            ]
            depth = np.maximum.reduce(parts)
            picture = a.base.max(axis=2) / 255.0
            image = Image.fromarray((picture * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(max(1.0, w / 60.0)))
            detail = np.asarray(image, dtype=np.float32) / 255.0
            depth = depth * (0.85 + 0.15 * detail)
            blur = Image.fromarray((np.clip(depth, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(max(1.0, w / 45.0)))
            self._depth = np.asarray(blur, dtype=np.float32) / 255.0
        return self._depth

    def turn_angle(self, now):
        """How far she is turned right now, from -1 (turned one way) to +1 (the other): slow, never quite repeating."""
        return max(-1.0, min(1.0, math.sin(now * 0.55) * 0.62 + math.sin(now * 0.23 + 1.0) * 0.38))

    def _turn(self, frame, now, swing=None, damp=True):
        """Turn her on the spot: near parts (nose, face, chest) slide further than far parts (hair, shoulders' edges) and the side facing
        away from the light dims a little, so she looks like a solid shape turning, not a flat picture sliding."""
        a = self.assets
        swing = self.turn_angle(now) if swing is None else swing
        amount = swing * a.width * TURN_SHIFT * ((1.0 - 0.75 * self.idle_mix) if damp else 1.0)   # the flip book already moves her, so the fake turn is smaller (not for a head shake: that should show)
        if abs(amount) < 0.05:
            return frame
        depth = self._depth_map()
        shift = (depth - 0.45) * amount                                               # pixels, per pixel
        w = a.width
        cols = np.arange(w, dtype=np.float32)[None, :] - shift                        # where each output pixel looks in the picture
        left = np.clip(np.floor(cols).astype(np.int32), 0, w - 1)
        right = np.clip(left + 1, 0, w - 1)
        frac = (cols - np.floor(cols))[..., None]
        rows = np.arange(a.height)[:, None]
        turned = frame[rows, left] * (1.0 - frac) + frame[rows, right] * frac
        # light from one side: the side that turns away from you gets darker, the near side a touch brighter
        across = (np.arange(w, dtype=np.float32)[None, :] / w - 0.5) * 2.0            # -1 (left) .. +1 (right)
        shade = 1.0 - 0.28 * swing * across * depth
        return turned * np.clip(shade, 0.55, 1.3)[..., None]

    def _sparks(self, now, front, behind):
        """A slow tornado of tiny lights. Every light has its own random life: where it is born, how fast it climbs, how fast it swirls, how
        wide it goes and how bright it is, and it picks new random values each time it is reborn. They start in the middle of the lower ring,
        spiral up round her (narrow low down, wider higher up) and fade out at the height of her chest, never higher. The far half of each turn
        goes behind her (dimmer), the near half in front."""
        a = self.assets
        cx = a.pad_left + a.width / 2.0
        y_ring = PAD_TOP + a.height + 14.0
        y_top = PAD_TOP + a.height * 0.64                                              # the top of her chest: nothing goes higher than this
        radius = a.width * 0.40
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
