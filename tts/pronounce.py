"""HOW SHE SAYS NUMBERS AND HARD WORDS (0.96.4). Applied to the text just before a voice reads it (tts/kokoro_tts.py); what is shown or logged is untouched.

1. Decimals: "7.9" becomes "7 point 9" and "28.4 million" becomes "28 point 4 million", so the point is never dropped ("seven nine"). The digits after the
   point are said one by one ("3.14" = "three point one four"). Left alone: IDs like 21.02.002, version numbers like 0.96.3, and a full stop at the end of a sentence.
2. Units: "500 m" -> "500 metres", "2 km" -> "2 kilometres", "1.2 g" -> "1 point 2 gee" (a lone letter is read as a letter otherwise).
3. Hard words: config/pronunciations.json lists Latin and game words (Fonticulua, Tectonicas, terraformable...) with a respelling the voice reads correctly,
   plus extra changes for the Australian voice only (metres). Edit that file to fix a word; an empty list switches it off.
"""
import json
import re

from core import paths
from core.logger import get_logger

log = get_logger("pronounce")

_DECIMAL = re.compile(r"(?<![\d.,])(\d+)\.(\d+)(?!\d|\.\d)")
_METRES = re.compile(r"(?<=\d)\s?m\b(?!\.\d)")
_KM = re.compile(r"(?<=\d)\s?km\b")
_GEE = re.compile(r"(?<=\d)\s?g\b(?!\w)")

_table = None
_compiled = {}


def _load():
    global _table
    if _table is None:
        try:
            with open(paths.ROOT / "config" / "pronunciations.json", encoding="utf-8") as handle:
                data = json.load(handle)
            _table = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            log.warning("Could not read config/pronunciations.json; hard words are read as written")
            _table = {}
    return _table


def reload():
    global _table
    _table = None
    _compiled.clear()


def _words(voice_name):
    key = voice_name or ""
    if key not in _compiled:
        table = _load()
        merged = {}
        merged.update({k: v for k, v in (table.get("words") or {}).items() if isinstance(v, str)})
        if key:
            merged.update({k: v for k, v in (table.get(key) or {}).items() if isinstance(v, str)})
        if merged:
            pattern = re.compile(r"\b(%s)\b" % "|".join(re.escape(w) for w in sorted(merged, key=len, reverse=True)))
            _compiled[key] = (pattern, merged)
        else:
            _compiled[key] = None
    return _compiled[key]


def _spoken_decimal(match):
    return "%s point %s" % (match.group(1), " ".join(match.group(2)))


def prepare(text, voice_name=""):
    """The text as it should be handed to the voice. Safe on anything: a failure returns the text unchanged."""
    if not text:
        return text
    try:
        out = _DECIMAL.sub(_spoken_decimal, text)
        out = _KM.sub(" kilometres", out)
        out = _METRES.sub(" metres", out)
        out = _GEE.sub(" gee", out)
        found = _words(voice_name)
        if found is not None:
            pattern, merged = found
            out = pattern.sub(lambda m: merged[m.group(1)], out)
        return out
    except Exception:
        log.debug("Could not prepare the text", exc_info=True)
        return text
