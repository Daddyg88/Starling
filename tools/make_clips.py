"""
Turns short videos of her (thinking, listening, pleased, bored...) into the 'pose clips' Starling plays at the right moments.

    python tools/make_clips.py thinking=Thinking.mp4 listening=Listening.mp4 pleased=Pleased.mp4 bored1=Bored.mp4 bored2=Bored2.mp4

The names on the left are the ones Starling knows: thinking, listening, pleased, bored1, bored2 (bored1 and bored2 are picked at random).
Each clip should start and end in her normal pose, with the watermark already removed. What this does (needs ffmpeg):
  * takes 12 pictures a second,
  * scales and moves each clip so she sits exactly where she does in her still picture (ui/assets/hologram/base.jpg), whatever shape the video was,
  * stores smaller JPEG pictures in ui/assets/hologram/clips/<name>/ and writes clips.json.
Clips you do not list are left alone, so you can replace one at a time.
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
KNOWN = ("thinking", "listening", "pleased", "bored1", "bored2")


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


def build(name, video, base, meta):
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", "fps=%d" % FPS, str(Path(tmp) / "f_%04d.png")], check=True)
        files = sorted(Path(tmp).glob("f_*.png"))
        if len(files) < 4:
            print("%s: too few pictures in %s" % (name, video))
            return
        frames = [Image.open(f).convert("RGB") for f in files]
        error, scale, move = best_fit(frames[0], base)
        print("%s: %d pictures, scale %.2f, move (%.0f, %.0f), match error %.1f (lower is better; 3 or less is good)" % (name, len(frames), scale, move[0], move[1], error))
        folder = ASSETS / "clips" / name
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("*.jpg"):
            old.unlink()
        for number, frame in enumerate(frames):
            fitted = mf.fit_to_base(frame, base.size, scale, move)
            fitted = fitted.resize((int(round(fitted.width * STORE_HEIGHT / fitted.height)), STORE_HEIGHT), Image.LANCZOS)
            fitted.save(folder / ("%03d.jpg" % number), quality=74, optimize=True)
    meta[name] = {"frames": len(frames), "fps": FPS}
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
    meta = {k: v for k, v in meta.items() if k in KNOWN}
    for name, video in pairs:
        if name not in KNOWN:
            print("unknown clip name %r (use one of %s)" % (name, ", ".join(KNOWN)))
            continue
        build(name, video, base, meta)
    meta["size"] = list(base.size)
    path.write_text(json.dumps(meta), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
