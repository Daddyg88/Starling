"""
Finds the picture for a ship. No window code here, so it is easy to test.

Pictures are looked for (in this order) in
    data/ship_pictures/     your own pictures (updates never delete this folder; used first)
    ui/assets/ships/        pictures that ship with Starling
A picture is named after the ship with letters and numbers only: anaconda.png, cobra3.png (Cobra Mark 3), type9heavy.jpg ...
The name she says is used ("Cobra Mark 3" -> cobra3), and so is the game's code ("cobramkiii"), so either works.
"""
import re
from pathlib import Path

from core import paths
from core.ships import ship_name

ASSETS = Path(__file__).resolve().parent / "assets" / "ships"
EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
ALIASES = {"eagle": ("eagle2",), "viper": ("viper3",), "cobramkiii": ("cobra3",), "cobramkiv": ("cobra4",),
           "explorernx": ("caspianexplorer",), "lakonminer": ("type11prospector",), "typex": ("alliancechieftain", "chieftain"),
           "lynxbloodline": ("lynxhighliner",), "panthermkii": ("pantherclipper2",)}
_MARK = re.compile(r"m(?:ar)?k\.?[\s_-]*(vi|iv|iii|ii|v|i|[1-6])(?![a-z])", re.I)
_ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6"}


def user_folder():
    return paths.DATA_DIR / "ship_pictures"


def slug(name):
    """'Cobra Mk III' / 'Cobra Mark 3' / 'cobramkiii' -> 'cobra3'; 'Type-9 Heavy' -> 'type9heavy'."""
    text = _MARK.sub(lambda m: _ROMAN.get(m.group(1).lower(), m.group(1)), str(name or ""))
    return re.sub(r"[^a-z0-9]", "", text.lower())


def candidates(code="", name=""):
    """File name stems to try, best first."""
    found = []
    for text in (name, ship_name(code) if code else "", code):
        stem = slug(text)
        if not stem:
            continue
        for option in (stem, stem + "1") + ALIASES.get(stem, ()):
            if option not in found:
                found.append(option)
    return found


def _find(folder, stem):
    for extension in EXTENSIONS:
        path = Path(folder) / (stem + extension)
        if path.is_file():
            return path
    return None


def picture_for(code="", name="", folders=None):
    """The picture file for this ship, or None (the Home page then draws a simple outline instead)."""
    folders = folders or (user_folder(), ASSETS)
    for stem in candidates(code, name):
        for folder in folders:
            found = _find(folder, stem)
            if found is not None:
                return found
    return None
