"""Make short head-movement clips (a glance, a tilt, a nod) from the head pictures made in ComfyUI.

Usage (from the Starling folder; needs numpy, Pillow and opencv-python):
    python tools/make_head_clips.py [--check]

Reads docs/head_sources/*.png (512 x 768, made from starling_base_512x768.png), and for each clip morphs her still picture
into the head pose and back (optical-flow morphing, so the head really moves instead of fading), then writes the clip into
ui/assets/hologram/clips with the same layout as tools/make_clips.py. --check only writes a contact sheet (check_head.png).
The tiny red speck some ComfyUI pictures have at the top edge is painted out.
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "ui" / "assets" / "hologram"
SOURCES = ROOT / "docs" / "head_sources"
SOURCE_FOLDERS = (SOURCES, ROOT / "docs" / "eye_sources", ROOT / "docs" / "mouth_sources")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_mouths  # noqa: E402  (the still picture, scaled the way the ComfyUI pictures were)
import make_clips  # noqa: E402  (fits a frame onto her still picture and writes a clip)

# clip name -> (source picture(s), seconds, seconds held at the pose)
# One picture: she goes from her still picture to the pose, holds, and comes back. Several pictures: she goes through them in
# order (a laugh shakes between its two pictures) and comes back.
CLIPS = {
    "glance_left": ("look_left", 2.0, 0.5),
    "glance_right": ("look_right", 2.0, 0.5),
    "tilt": ("tilt_left", 2.4, 0.7),
    "nod": ("nod_down", 1.0, 0.1),
    "brow_up": ("brow_up", 1.8, 0.6),                  # eyebrows lifted: surprise or interest
    "brow_down": ("brow_down", 1.8, 0.6),              # eyebrows lowered: a frown, disappointment
    "eyes_left": ("eyes_left", 1.6, 0.5),              # only the eyes look aside (the head stays)
    "eyes_right": ("eyes_right", 1.6, 0.5),
    "wink": ("wink", 1.3, 0.25),
    "smirk": ("smirk", 2.0, 0.8),
    "sad": ("sad", 3.0, 1.4),
    "angry": ("angry", 2.0, 0.9),
    "worried": ("worried", 2.2, 1.0),
    "yawn": ("yawn", 3.2, 1.3),
    "awe": ("awe", 2.8, 1.3),
    "ponder": ("thinking_look", 2.6, 1.2),
    "eyeroll": ("eyeroll", 1.6, 0.4),
    "blush": ("shy", 2.4, 1.0),
    "sleepy": ("eyes_half", 3.0, 1.4),
    "glance_up": ("look_up", 2.0, 0.5),                # the unused pictures
    "tilt_right": ("tilt_right", 2.4, 0.7),
    "eyes_up": ("eyes_up", 1.6, 0.5),
    "eyes_down": ("eyes_down", 1.6, 0.5),
    "nod_twice": (("nod_down", "look_up", "nod_down", "look_up"), 2.4, 0.0),      # a yes with a little more feeling
    "suspicious": (("brow_down", "eyes_left", "eyes_right", "eyes_left", "brow_down"), 3.4, 0.0),   # narrow look, eyes flick aside
    "curious": (("tilt_left", "brow_up", "tilt_right", "brow_up"), 3.4, 0.0),
    "giggle": (("shy", "laugh_a", "shy", "laugh_a"), 3.0, 0.0),
    "flirty": (("wink", "smirk", "shy", "wink"), 3.4, 0.0),
    "disagree": (("look_left", "look_right", "look_left", "look_right"), 2.8, 0.0),   # a head shake, "no"
    "daydream": (("look_up", "thinking_look", "eyes_half", "look_up"), 4.0, 0.0),
    "laugh": (("laugh_a", "laugh_b", "laugh_a", "laugh_b", "laugh_a"), 2.6, 0.0),
}
FPS = 12


def clean(picture):
    """Paint out stray bright red pixels (a ComfyUI speck) with the dark background."""
    a = np.asarray(picture.convert("RGB")).copy()
    red = (a[..., 0] > 100) & (a[..., 0] > a[..., 2] + 30)
    red[16:] = False                                         # only the top edge (her eyes have a little orange in them)
    if red.any():
        ys, xs = np.nonzero(red)
        a[max(0, ys.min() - 3):ys.max() + 4, max(0, xs.min() - 3):xs.max() + 4] = 0
    return Image.fromarray(a)


def warp(image, flow, amount):
    import cv2
    h, w = flow.shape[:2]
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return cv2.remap(image, gx + flow[..., 0] * amount, gy + flow[..., 1] * amount, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def morph_frames(start, end, count):
    """count pictures going from start to end; the head moves (flow), the colour fades."""
    import cv2
    a, b = np.asarray(start.convert("RGB")), np.asarray(end.convert("RGB"))
    ga, gb = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY), cv2.cvtColor(b, cv2.COLOR_RGB2GRAY)
    ab = cv2.calcOpticalFlowFarneback(gb, ga, None, 0.5, 4, 25, 5, 7, 1.5, 0)      # for each pixel of the middle picture: where to look in start
    ba = cv2.calcOpticalFlowFarneback(ga, gb, None, 0.5, 4, 25, 5, 7, 1.5, 0)
    frames = []
    for i in range(count):
        t = i / float(max(1, count - 1))
        mix = (1 - t) * warp(a, ab, t).astype(np.float32) + t * warp(b, ba, 1 - t).astype(np.float32)
        frames.append(Image.fromarray(np.clip(mix, 0, 255).astype(np.uint8)))
    return frames


def ease(x):
    return x * x * (3 - 2 * x)


def find_source(source):
    for folder in SOURCE_FOLDERS:
        if (folder / ("%s.png" % source)).exists():
            return folder / ("%s.png" % source)
    return None


def build_sequence(sources, seconds, still):
    """Through several pictures one after the other (a laugh): still -> first, between them, last -> still."""
    poses = [still] + [clean(Image.open(find_source(n)).convert("RGB")) for n in sources] + [still]
    total = max(len(poses) - 1, int(round(seconds * FPS)))
    per = max(2, total // (len(poses) - 1))
    frames = []
    for a, b in zip(poses, poses[1:]):
        frames += morph_frames(a, b, per + 1)[:-1]
    return frames + [still]


def build(name, source, seconds, hold, base, still):
    if isinstance(source, tuple):
        return build_sequence(source, seconds, still)
    pose = clean(Image.open(find_source(source)).convert("RGB"))
    total = max(4, int(round(seconds * FPS)))
    held = int(round(hold * FPS))
    move = max(2, (total - held) // 2)
    out = morph_frames(still, pose, 9)                              # nine steps from her still picture to the pose
    frames = []
    for i in range(move):                                           # there ...
        frames.append(out[int(round(ease(i / float(move - 1)) * 8))])
    frames += [out[8]] * held                                       # ... hold ...
    for i in range(total - move - held):                            # ... and back
        frames.append(out[int(round(ease(1 - i / float(max(1, total - move - held - 1))) * 8))])
    return frames


def main(argv):
    check = "--check" in argv
    base = Image.open(ASSETS / "base.jpg").convert("RGB")
    still = make_mouths.to_small(base)
    results = {}
    for name, (source, seconds, hold) in CLIPS.items():
        names = source if isinstance(source, tuple) else (source,)
        if any(find_source(n) is None for n in names):
            print("missing a picture for", name)
            continue
        results[name] = build(name, source, seconds, hold, base, still)
        print("%-12s %d pictures" % (name, len(results[name])))
    if check:
        tiles = []
        for name, frames in results.items():
            row = [frames[i].resize((120, 180)) for i in np.linspace(0, len(frames) - 1, 9).astype(int)]
            tiles.append(row)
        sheet = Image.new("RGB", (120 * 9, 180 * len(tiles)))
        for r, row in enumerate(tiles):
            for c, tile in enumerate(row):
                sheet.paste(tile, (c * 120, r * 180))
        sheet.save(ROOT / "check_head.png")
        print("wrote", ROOT / "check_head.png")
        return 0
    meta_path = ASSETS / "clips.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    for name, frames in results.items():
        make_clips.write_clip(name, frames, base, meta, "loop")      # they already end where they began
    meta["size"] = list(base.size)
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
