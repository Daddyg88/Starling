"""
Turns short videos of her (thinking, listening, pleased, bored...) into the 'pose clips' Starling plays at the right moments.

    python tools/make_clips.py thinking=Thinking.mp4 listening=Listening.mp4 pleased=Pleased.mp4 salute=Salute.mp4 bored1=Bored.mp4 bored2=Bored2.mp4

The names on the left are the ones Starling knows: thinking, listening, pleased, salute, bored1, bored2 (bored1 and bored2 are picked at random).
Each clip should start and end in her normal pose, with the watermark already removed. What this does (needs ffmpeg):
  * takes 12 pictures a second,
  * scales and moves each clip so she sits exactly where she does in her still picture (ui/assets/hologram/base.jpg), whatever shape the video was,
  * stores smaller JPEG pictures in ui/assets/hologram/clips/<name>/ and writes clips.json.
Clips you do not list are left alone, so you can replace one at a time.
A clip that does not end where it began is played forwards and then BACKWARDS (no extra pictures are stored), so she always ends in her normal pose.
You can force this either way: pleased=Pleased.mp4:back (always play back) or pleased=Pleased.mp4:loop (never).
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_flipbook as mf          # noqa: E402  (the same fitting helpers the idle loop uses)

ASSETS = mf.ASSETS
FPS = 12
STORE_HEIGHT = 480
WIDE = ("salute",)               # clips with an arm that reaches beyond her picture: stored with room at the sides
PAD = (0.52, 0.06)               # that room, as a fraction of her picture width (left, right); her window is made this much wider
KNOWN = ("thinking", "listening", "pleased", "bored1", "bored2", "salute",      # the first set
         "nod", "shake", "startle", "tilt", "glance_left", "glance_right", "brow_up", "brow_down", "eyes_left", "eyes_right", "ponder", "yawn", "laugh", "wink", "smirk", "blush", "blow_kiss", "eyeroll", "facepalm", "shrug", "sad", "worried", "angry",
         "awe", "excited", "sleepy", "hair_flick", "hand_to_temple", "hands_resting", "content_smile", "listen_tilt", "glance_up", "tilt_right", "eyes_up", "eyes_down", "nod_twice", "suspicious", "curious", "giggle", "flirty", "disagree", "daydream", "point", "thumbs_up", "facing_away", "cheer", "idle_alt1")          # see docs/CLIP_SHOT_LIST.md
BACK_GAP = 3.0                   # if a clip ends this much (average brightness difference) away from where it began, play it back in reverse to get her home


def best_fit(first, base):
    """Scale and move that put the clip's first picture on top of her still picture."""
    base_gray = np.asarray(base.convert("L"), dtype=np.float32)
    best = None
    for scale in np.arange(0.70, 1.31, 0.01):
        fitted = np.asarray(mf.fit_to_base(first, base.size, scale, (0, 0)).convert("L"), dtype=np.float32)
        dx, dy = mf.shift_between(mf.crop(base_gray), mf.crop(fitted))
        moved = np.asarray(mf.fit_to_base(first, base.size, scale, (-dx, -dy)).convert("L"), dtype=np.float32)
        error = float(np.abs(mf.crop(moved) - mf.crop(base_gray)).mean())
        if best is None or error < best[0]:
            best = (error, float(scale), (-dx, -dy))
    return best


def fit_wide(frame, base_size, scale, move):
    """Like fit_to_base, but on a canvas with PAD room at each side, so an arm that goes past her picture is kept."""
    bw, bh = base_size
    left, right = int(round(PAD[0] * bw)), int(round(PAD[1] * bw))
    k = bh / float(frame.height) * scale
    resized = frame.resize((max(1, int(round(frame.width * k))), max(1, int(round(frame.height * k)))), Image.LANCZOS)
    canvas = Image.new("RGB", (bw + left + right, bh), (0, 0, 0))
    canvas.paste(resized, (int(round((bw - resized.width) / 2.0 + move[0])) + left, int(round((bh - resized.height) / 2.0 + move[1]))))
    return canvas


def end_gap(frames):
    """How different the last picture is from the first (average brightness difference on small grey copies; 0 = identical)."""
    def small(f):
        return np.asarray(f.convert("L").resize((64, 96), Image.BILINEAR), dtype=np.float32)
    return float(np.abs(small(frames[0]) - small(frames[-1])).mean())


def build(name, video, base, meta, mode=""):
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", "fps=%d" % FPS, str(Path(tmp) / "f_%04d.png")], check=True)
        files = sorted(Path(tmp).glob("f_*.png"))
        if len(files) < 4:
            print("%s: too few pictures in %s" % (name, video))
            return
        frames = [Image.open(f).convert("RGB") for f in files]
    write_clip(name, frames, base, meta, mode)


def write_clip(name, frames, base, meta, mode=""):
    """Fit the pictures onto her still picture and store them as the clip `name` (also used by tools/make_head_clips.py)."""
    if True:
        gap = end_gap(frames)
        back = mode == "back" or (mode != "loop" and gap > BACK_GAP)
        error, scale, move = best_fit(frames[0], base)
        print("%s: %d pictures, scale %.2f, move (%.0f, %.0f), match error %.1f (lower is better; 3 or less is good); ends %.1f away from the start -> %s" % (
            name, len(frames), scale, move[0], move[1], error, gap, "plays forwards then back" if back else "plays as it is"))
        folder = ASSETS / "clips" / name
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.jpg"):
            old.unlink()
        for number, frame in enumerate(frames):
            fitted = fit_wide(frame, base.size, scale, move) if name in WIDE else mf.fit_to_base(frame, base.size, scale, move)
            fitted = fitted.resize((int(round(fitted.width * STORE_HEIGHT / fitted.height)), STORE_HEIGHT), Image.LANCZOS)
            fitted.save(folder / ("%03d.jpg" % number), quality=74, optimize=True)
    meta[name] = {"frames": len(frames), "fps": FPS}
    if back:
        meta[name]["back"] = True
    if name in WIDE:
        meta[name]["wide"] = True
        meta["pad"] = list(PAD)
    size = sum(p.stat().st_size for p in folder.glob("*.jpg")) / 1e6
    print("  wrote %.1f MB" % size)


def main(argv):
    pairs = [a.split("=", 1) for a in argv[1:] if "=" in a]
    if not pairs:
        print(__doc__)
        return 1
    base = Image.open(ASSETS / "base.jpg").convert("RGB")
    path = ASSETS / "clips.json"
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    meta = {k: v for k, v in meta.items() if k in KNOWN or k == "pad"}
    for name, video in pairs:
        mode = ""
        for suffix in ("back", "loop"):                      # name=file.mp4:back (a Windows path like C:\x.mp4 has no such ending)
            if video.endswith(":" + suffix):
                video, mode = video[:-len(suffix) - 1], suffix
        if name not in KNOWN:
            print("unknown clip name %r (use one of %s)" % (name, ", ".join(KNOWN)))
            continue
        build(name, video, base, meta, mode)
    meta["size"] = list(base.size)
    path.write_text(json.dumps(meta), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
