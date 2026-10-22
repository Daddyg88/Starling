"""
Downloads the ship pictures from the Elite Dangerous wiki into data/ship_pictures/ (run_get_ship_pictures.bat).

It reads https://elite-dangerous.fandom.com/wiki/Ships, finds each ship's picture and saves it named after the ship
(anaconda.png, cobra3.png ...). It only uses the standard Python library, so nothing needs installing. Run it again any time;
pictures you already have are skipped. If the wiki changes its page layout and nothing downloads, you can put pictures in
data/ship_pictures/ by hand instead (see ui/assets/ships/README.txt).
"""
import re
import sys
import time
import urllib.request
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ui.ship_pictures import slug, user_folder      # noqa: E402

PAGE = "https://elite-dangerous.fandom.com/wiki/Ships"
HEADERS = {"User-Agent": "Mozilla/5.0 (Starling ship picture fetcher)"}
SKIP = ("icon", "logo", "wiki", "thargoid", "banner", "placeholder")


def fetch(url, binary=False):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as reply:
        data = reply.read()
    return data if binary else data.decode("utf-8", "replace")


def find_pictures(html):
    """[(ship name, full-size url)] from the page's <img> tags."""
    found, seen = [], set()
    for tag in re.findall(r"<img\b[^>]*>", html, re.I):
        attrs = {k.lower(): unescape(v) for k, v in re.findall(r'([\w-]+)\s*=\s*"([^"]*)"', tag)}
        url = attrs.get("data-src") or attrs.get("src") or ""
        if "static.wikia.nocookie.net" not in url or url.startswith("data:"):
            continue
        name = attrs.get("data-image-name") or attrs.get("alt") or ""
        name = re.sub(r"\.(png|jpe?g|webp|gif)$", "", name, flags=re.I).strip()
        if not name or any(word in name.lower() for word in SKIP):
            continue
        url = re.sub(r"/scale-to-width-down/\d+", "", url)
        url = re.sub(r"/smart/width/\d+/height/\d+", "", url)
        key = slug(name)
        if key and key not in seen:
            seen.add(key)
            found.append((name, url))
    return found


def main():
    folder = user_folder()
    folder.mkdir(parents=True, exist_ok=True)
    print("Reading the ship list from the wiki...")
    try:
        pictures = find_pictures(fetch(PAGE))
    except Exception as problem:                              # network down, wiki blocked, ...
        print("Could not read the wiki page: %s" % problem)
        return 1
    if not pictures:
        print("The page did not list any pictures (the wiki may have changed). Put pictures in %s by hand instead." % folder)
        return 1
    done = 0
    for name, url in pictures:
        target = folder / (slug(name) + ".png")
        if any((folder / (slug(name) + ext)).exists() for ext in (".png", ".jpg", ".jpeg", ".webp")):
            continue
        try:
            data = fetch(url, binary=True)
            try:                                              # keep the files small: 600 pixels wide is plenty
                from io import BytesIO
                from PIL import Image
                picture = Image.open(BytesIO(data)).convert("RGBA")
                picture.thumbnail((600, 600))
                picture.save(target)
            except Exception:
                target = folder / (slug(name) + ".png")
                target.write_bytes(data)
            done += 1
            print("  saved %s" % target.name)
            time.sleep(0.3)
        except Exception as problem:
            print("  could not get %s: %s" % (name, problem))
    print("Done: %d new pictures in %s" % (done, folder))
    return 0


if __name__ == "__main__":
    sys.exit(main())
