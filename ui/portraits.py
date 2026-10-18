"""
Her picture for each mood. No window code here, so it is easy to test.

Pictures live in ui/assets/portraits/ and are named after the mood: Close, Friendly, Neutral, Sarcastic, Frustrated
(.png, .jpg, .jpeg or .webp). A mood without its own picture uses Neutral; if that is missing too, ui/assets/avatar.png.
"""

from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets"
PORTRAITS = ASSETS / "portraits"
MOODS = ("Close", "Friendly", "Neutral", "Sarcastic", "Frustrated")
EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


def _find(folder, name):
    for extension in EXTENSIONS:
        for candidate in (name + extension, name.lower() + extension):
            path = Path(folder) / candidate
            if path.is_file():
                return path
    return None


def portrait_for(mood, folder=None):
    """The picture file for this mood, or None if there are no pictures at all."""
    folder = Path(folder) if folder is not None else PORTRAITS
    mood = mood if mood in MOODS else "Neutral"
    found = _find(folder, mood) or _find(folder, "Neutral")
    if found is None and (ASSETS / "avatar.png").is_file():
        found = ASSETS / "avatar.png"
    return found


def fit(width, height, box_width, box_height):
    """Scale (width, height) to sit inside the box, keeping its shape."""
    if width <= 0 or height <= 0:
        return box_width, box_height
    scale = min(box_width / width, box_height / height)
    return max(1, int(width * scale)), max(1, int(height * scale))
