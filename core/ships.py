"""
Ship names, said and shown properly - including ships that did not exist when Starling was written.

The game's journal names ships like "anaconda", "cobramkiii", "type9_military" or "python_nx". This turns them into names she can
say ("Anaconda", "Cobra Mark 3", "Type 10 Defender", "Python Mark 2").

  1. If the game gives the proper name ("Ship_Localised"), that is used.
  2. Otherwise config/ships.json is checked (known ships, and anything you add).
  3. Otherwise she works it out from the code name ("anaconda_mkii" -> "Anaconda Mark 2"), so a brand new ship is
     recognised on day one without an update. If she says one oddly, add it to config/ships.json.
"""
import json
import re

from core import paths
from core.logger import get_logger

log = get_logger("ships")

_ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "1": "1", "2": "2", "3": "3", "4": "4", "5": "5", "6": "6"}
_MARK = re.compile(r"[\s_\-]*\bmk\.?[\s_\-]*(vi|iv|v|iii|ii|i|[1-6])\b|[\s_\-]*mk(vi|iv|v|iii|ii|i|[1-6])$", re.I)
_MARK_SPOKEN = re.compile(r"\s*\bmark\s+(vi|iv|v|iii|ii|i|[1-6])\b", re.I)

_table = None


def _load(path=None):
    path = path or (paths.CONFIG_DIR / "ships.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return {str(k).lower(): str(v) for k, v in (data.get("ships") or {}).items()}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, AttributeError):
        log.exception("Could not read %s", path)
        return {}


def known():
    global _table
    if _table is None:
        _table = _load()
    return _table


def reload(path=None):
    global _table
    _table = _load(path)


def _marks(text):
    """'Anaconda Mk II' / 'CobraMkIII' / 'Mk. 4' -> '... Mark 2' (so the voice says Mark, not 'M K')."""
    def swap(match):
        number = match.group(1) or match.group(2)
        return " Mark " + _ROMAN.get(number.lower(), number)
    return _MARK.sub(swap, text).strip()


def _from_code(code):
    text = re.sub(r"[$;]", "", code.strip().lower())
    text = re.sub(r"_name$", "", text)
    text = _marks(text)
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"^type\s*(\d+)", r"Type \1", text)
    text = re.sub(r"\s+", " ", text).strip()
    words = [w if (w.startswith("Type") or w == "Mark" or w.isdigit()) else w.capitalize() for w in text.split(" ")]
    return " ".join(words)


def ship_name(raw, localised=None):
    """The name she says. Never fails; an empty input gives ''."""
    if localised and str(localised).strip():
        return _marks(str(localised).strip())
    raw = str(raw or "").strip()
    if not raw:
        return ""
    if raw != raw.lower() and " " in raw:          # already a proper name ("Federal Corvette")
        return _marks(raw)
    key = re.sub(r"[$;]|_name$", "", raw.lower())
    table = known()
    if key in table:
        return table[key]
    return _from_code(raw)
