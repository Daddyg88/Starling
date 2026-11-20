"""Turn mouth pictures made in ComfyUI (the Expression Editor) into Starling's mouth cut-outs.

Usage (from the Starling folder; needs Pillow and numpy only):
    python tools/make_mouths.py FOLDER
FOLDER holds 512 x 768 pictures of her (made from starling_base_512x768.png) named
    ah.png eh.png ee.png oh.png oo.png pressed.png fv.png smile.png   (mouths)
    eyes_closed.png   (her blink: the eyes shut)
(any of them; the ones you leave out are left alone). The mouth area is cut from each, lined up with her still picture,
its colour matched to the still picture, and written to ui/assets/hologram/<name>.png. Add --check to only print the numbers
and write a picture of the result to FOLDER/check.png without changing anything.
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ASSETS = Path(__file__).resolve().parent.parent / "ui" / "assets" / "hologram"
NAMES = ("ah", "eh", "ee", "oh", "oo", "pressed", "fv", "smile")
BOX = (270, 330, 250, 200)                    # where the mouth cut-outs sit on her 784 x 1168 base picture (hologram.json)
EYES_BOX = (270, 245, 250, 100)               # and where the closed-eyes cut-out sits (the blink)
EYES_FILES = ("eyes_closed", "eyes")          # either file name makes the blink picture; the face is lined up on the nose and mouth instead of the eyes
OUT_W, OUT_H = 512, 768                       # the size of the ComfyUI pictures
SX, SY = 516 / 784.0, 768 / 1168.0            # base picture -> the 512 x 768 picture (scaled to 768 tall, then 2 pixels cropped each side)
CROP_X = 2


def to_small(base):
    """Her still picture the way the ComfyUI picture was made from it (so the two can be compared)."""
    return base.resize((516, 768), Image.LANCZOS).crop((CROP_X, 0, CROP_X + OUT_W, OUT_H))


def grey(image, box):
    return np.asarray(image.convert("L").crop(box), dtype=np.float32)


def find_shift(reference, picture, reach=8, box=(150, 110, 370, 235)):
    """How far the face in the new picture has moved from the still picture. Normally it looks at the eyes and nose (the mouth changes);
    for the eyes it looks at the nose and mouth instead."""
    want = grey(reference, box)
    best = (1e9, 0, 0)
    for dy in range(-reach, reach + 1):
        for dx in range(-reach, reach + 1):
            moved = grey(picture, (box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy))
            error = float(np.abs(moved - want).mean())
            if error < best[0]:
                best = (error, dx, dy)
    return best


def cut(picture, dx, dy, box=BOX):
    """The box, cut from the ComfyUI picture and scaled back up to full size (bicubic)."""
    x0 = box[0] * SX - CROP_X + dx
    y0 = box[1] * SY + dy
    return picture.transform((box[2], box[3]), Image.AFFINE, (SX, 0, x0, 0, SY, y0), resample=Image.BICUBIC)


def make(name, picture, base, alpha_from, check=False, box=BOX, shift_box=(150, 110, 370, 235)):
    reference = to_small(base)
    error, dx, dy = find_shift(reference, picture, box=shift_box)
    sprite = np.asarray(cut(picture.convert("RGB"), dx, dy, box), dtype=np.float32)
    still = np.asarray(base.crop((box[0], box[1], box[0] + box[2], box[1] + box[3])).convert("RGB"), dtype=np.float32)
    alpha = np.asarray(alpha_from)[..., 3].astype(np.float32) / 255.0
    outside = alpha < 0.15                                           # skin around the mouth: should look the same as the still picture
    offset = (still[outside] - sprite[outside]).mean(axis=0) if outside.sum() > 50 else np.zeros(3)
    sprite = np.clip(sprite + offset, 0, 255)
    rgba = np.dstack([sprite, alpha * 255.0]).astype(np.uint8)
    print("%-8s shift (%+d, %+d) px, face match error %.1f, colour shift (%+.0f %+.0f %+.0f)" % (name, dx, dy, error, *offset))
    return Image.fromarray(rgba, "RGBA")


def main(argv):
    check = "--check" in argv
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 1
    folder = Path(args[0])
    base = Image.open(ASSETS / json.loads((ASSETS / "hologram.json").read_text(encoding="utf-8"))["base"]).convert("RGB")
    old_alpha = Image.open(ASSETS / "ah.png").convert("RGBA")
    made = {}
    for name in NAMES:
        path = folder / ("%s.png" % name)
        if not path.exists():
            continue
        picture = Image.open(path)
        if picture.size != (OUT_W, OUT_H):
            print("%s: the picture is %d x %d but should be %d x %d, skipped" % (name, picture.width, picture.height, OUT_W, OUT_H))
            continue
        existing = ASSETS / ("%s.png" % name)
        alpha_from = Image.open(existing).convert("RGBA") if existing.exists() else old_alpha
        made[name] = make(name, picture, base, alpha_from, check)
    for file_name in EYES_FILES:                                      # the blink picture
        path = folder / ("%s.png" % file_name)
        if path.exists() and "eyes" not in made:
            picture = Image.open(path)
            if picture.size != (OUT_W, OUT_H):
                print("%s: the picture is %d x %d but should be %d x %d, skipped" % (file_name, picture.width, picture.height, OUT_W, OUT_H))
                continue
            made["eyes"] = make("eyes", picture, base, Image.open(ASSETS / "eyes.png").convert("RGBA"), check, EYES_BOX, (160, 215, 360, 300))
    if not made:
        print("No pictures found in", folder)
        return 1
    if check:
        # a picture of the result: her still face with each new mouth on it
        face = base.crop((200, 220, 590, 560))
        sheet = Image.new("RGB", (face.width * len(made), face.height))
        for i, (name, sprite) in enumerate(made.items()):
            tile = face.copy()
            at = EYES_BOX if name == "eyes" else BOX
            tile.paste(sprite.convert("RGB"), (at[0] - 200, at[1] - 220), sprite.split()[3])
            sheet.paste(tile, (i * face.width, 0))
        sheet.save(folder / "check.png")
        print("wrote", folder / "check.png")
        return 0
    for name, sprite in made.items():
        sprite.save(ASSETS / ("%s.png" % name))
    print("wrote %d mouth pictures to %s" % (len(made), ASSETS))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
