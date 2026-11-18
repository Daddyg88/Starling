"""
Turns an idle video of her (mp4/gif) into the 'flip book' Starling plays while she is quiet.

    python tools/make_flipbook.py path/to/clip.mp4 [first_frame last_frame]

What it does: pulls out the frames (needs ffmpeg), lines each one up with her still picture (ui/assets/hologram/base.jpg),
works out how far her head has moved in every frame (so the mouth and eye pictures can follow it), joins the end of the
loop back to its start with a short cross-fade, and writes ui/assets/hologram/idle/*.jpg and idle.json.
Run it on a PC with ffmpeg; the result is plain pictures, nothing else is needed to play it.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ASSETS = Path(__file__).resolve().parent.parent / "ui" / "assets" / "hologram"
FACE = (0.10, 0.46, 0.25, 0.75)          # rows from..to, columns from..to (as fractions of her picture): where the head is
CROSSFADE = 12                           # frames at the end that are blended back into the start
FPS = 30
STORE_HEIGHT = 840                       # the pictures are stored a little smaller than her still picture (she is never shown larger than this)


def shift_between(a, b):
    """How many pixels b is moved (dx, dy) compared with a, by phase correlation. Both are float grayscale arrays of the same size."""
    fa, fb = np.fft.fft2(a - a.mean()), np.fft.fft2(b - b.mean())
    cross = fa * np.conj(fb)
    cross /= np.abs(cross) + 1e-6
    corr = np.fft.ifft2(cross).real
    y, x = np.unravel_index(np.argmax(corr), corr.shape)
    h, w = corr.shape
    if y > h // 2:
        y -= h
    if x > w // 2:
        x -= w
    return -float(x), -float(y)           # b = a moved by (+dx, +dy)  ->  the peak sits at (-dx, -dy)


def crop(gray):
    h, w = gray.shape
    return gray[int(h * FACE[0]):int(h * FACE[1]), int(w * FACE[2]):int(w * FACE[3])]


def fit_to_base(frame, base_size, scale, move):
    """The clip frame, scaled and moved onto a canvas the size of her still picture."""
    bw, bh = base_size
    k = bh / float(frame.height) * scale
    resized = frame.resize((max(1, int(round(frame.width * k))), max(1, int(round(frame.height * k)))), Image.LANCZOS)
    canvas = Image.new("RGB", base_size, (0, 0, 0))
    canvas.paste(resized, (int(round((bw - resized.width) / 2.0 + move[0])), int(round((bh - resized.height) / 2.0 + move[1]))))
    return canvas


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    clip = argv[1]
    base = Image.open(ASSETS / "base.jpg").convert("RGB")
    base_gray = np.asarray(base.convert("L"), dtype=np.float32)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["ffmpeg", "-v", "error", "-i", clip, "-vf", "fps=%d" % FPS, str(Path(tmp) / "f_%04d.png")], check=True)
        files = sorted(Path(tmp).glob("f_*.png"))
        frames = [Image.open(f).convert("RGB") for f in files]
        first = int(argv[2]) if len(argv) > 3 else 0
        last = int(argv[3]) if len(argv) > 3 else len(frames) - 1
        frames = frames[first:last + 1]
        print("%d frames used" % len(frames))
        # best overall size and position against the still picture, measured on the middle frame
        middle = frames[len(frames) // 2]
        best = None
        for scale in np.arange(0.94, 1.081, 0.01):
            fitted = np.asarray(fit_to_base(middle, base.size, scale, (0, 0)).convert("L"), dtype=np.float32)
            dx, dy = shift_between(crop(base_gray), crop(fitted))
            moved = np.asarray(fit_to_base(middle, base.size, scale, (-dx, -dy)).convert("L"), dtype=np.float32)
            error = float(np.abs(crop(moved) - crop(base_gray)).mean())
            if best is None or error < best[0]:
                best = (error, scale, (-dx, -dy))
        _, scale, move = best
        print("fit: scale %.2f, move %s" % (scale, move))
        fitted = [fit_to_base(f, base.size, scale, move) for f in frames]
    # a loop with no jump: the last CROSSFADE frames are blended into the frames that follow the loop's first frame
    total = len(fitted) - CROSSFADE
    arrays = [np.asarray(f, dtype=np.float32) for f in fitted]
    looped = []
    for i in range(total):
        if i < CROSSFADE:
            alpha = i / float(CROSSFADE)                       # 0: still the tail of the clip, 1: the clip's own frame
            looped.append(arrays[total + i] * (1.0 - alpha) + arrays[i] * alpha)
        else:
            looped.append(arrays[i])
    shifts = []
    reference = crop(base_gray)
    for frame in looped:
        gray = np.asarray(Image.fromarray(frame.astype(np.uint8)).convert("L"), dtype=np.float32)
        dx, dy = shift_between(reference, crop(gray))
        shifts.append([round(dx, 1), round(dy, 1)])
    folder = ASSETS / "idle"
    folder.mkdir(exist_ok=True)
    for old in folder.glob("*.jpg"):
        old.unlink()
    for number, frame in enumerate(looped):
        picture = Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8))
        picture = picture.resize((int(round(picture.width * STORE_HEIGHT / picture.height)), STORE_HEIGHT), Image.LANCZOS)
        picture.save(folder / ("%03d.jpg" % number), quality=78, optimize=True)
    (ASSETS / "idle.json").write_text(json.dumps({"fps": FPS, "frames": len(looped), "size": list(base.size), "shifts": shifts}), encoding="utf-8")
    size = sum(p.stat().st_size for p in folder.glob("*.jpg")) / 1e6
    print("wrote %d frames (%.1f MB). Head moves: x %.1f..%.1f, y %.1f..%.1f px" % (
        len(looped), size, min(s[0] for s in shifts), max(s[0] for s in shifts), min(s[1] for s in shifts), max(s[1] for s in shifts)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
