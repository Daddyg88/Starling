"""
Her picture for each mood. No window code here, so it is easy to test.

Pictures are named after the mood: Infatuated, Close, Friendly, Neutral, Sarcastic, Frustrated, Upset (.png, .jpg, .jpeg or .webp).
A mood without its own picture uses its parent mood, then Neutral; if that is missing too, avatar.png.
YOUR OWN pictures go in data/portraits/ (0.96.50): an update replaces the program folder but keeps data/, so they stay. Whatever is in
data/portraits/ is used first; the pictures that come with her (ui/assets/portraits/) are the fallback.
"""

from pathlib import Path

from core import paths
from personality.moods import PARENT

ASSETS = Path(__file__).resolve().parent / "assets"
PORTRAITS = ASSETS / "portraits"
USER_PORTRAITS = paths.DATA_DIR / "portraits"           # your own pictures: data/ survives every update, ui/assets/ does not
MOODS = ("Infatuated", "Close", "Friendly", "Neutral", "Sarcastic", "Frustrated", "Upset")
EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


def _find(folder, name):
    for extension in EXTENSIONS:
        for candidate in (name + extension, name.lower() + extension):
            path = Path(folder) / candidate
            if path.is_file():
                return path
    return None


def _chain(folder, mood):
    return _find(folder, mood) or _find(folder, PARENT.get(mood, "Neutral")) or _find(folder, "Neutral")


def portrait_for(mood, folder=None, user_folder=None):
    """The picture file for this mood, or None if there are no pictures at all. Your own (data/portraits/) win over the ones that come with her.
    Giving `folder` (tests) looks only there."""
    mood = mood if mood in MOODS else "Neutral"
    if folder is not None:
        found = _chain(Path(folder), mood)
    else:
        mine = Path(user_folder) if user_folder is not None else USER_PORTRAITS
        found = _chain(mine, mood) or _find(mine, "avatar") or _chain(PORTRAITS, mood)
    if found is None and (ASSETS / "avatar.png").is_file():
        found = ASSETS / "avatar.png"
    return found


def fit(width, height, box_width, box_height):
    """Scale (width, height) to sit inside the box, keeping its shape."""
    if width <= 0 or height <= 0:
        return box_width, box_height
    scale = min(box_width / width, box_height / height)
    return max(1, int(width * scale)), max(1, int(height * scale))
