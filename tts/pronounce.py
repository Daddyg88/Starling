"""HOW SHE SAYS NUMBERS AND HARD WORDS (0.96.4). Applied to the text just before a voice reads it (tts/kokoro_tts.py); what is shown or logged is untouched.

1. Decimals: "7.9" becomes "7 point 9" and "28.4 million" becomes "28 point 4 million", so the point is never dropped ("seven nine"). The digits after the
   point are said one by one ("3.14" = "three point one four"). Left alone: IDs like 21.02.002, version numbers like 0.96.3, and a full stop at the end of a sentence.
2. Units: "500 m" -> "500 metres", "2 km" -> "2 kilometres", "1.2 g" -> "1 point 2 gee" (a lone letter is read as a letter otherwise).
3. (0.96.51) Years are said as years ("in 1994" = "nineteen ninety-four", Elite's "in 3125" = "thirty-one twenty-five"), dates as ordinals ("16th" =
   "sixteenth"), and Elite system codes letter by letter ("NL-N C23-4" = "N L, N, C 2 3, 4"). Acronyms such as SRV and DSSA are in the word list below.
4. Hard words: config/pronunciations.json lists Latin and game words (Fonticulua, Tectonicas, terraformable...) with a respelling the voice reads correctly,
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

_YEAR = re.compile(r"(?<![\d.,$#/-])\b(?:(?<=in )|(?<=of )|(?<=by )|(?<=since )|(?<=until )|(?<=from )|(?<=and )|(?<=during )|(?<=before )|(?<=after )"
                   r"|(?<=January )|(?<=February )|(?<=March )|(?<=April )|(?<=May )|(?<=June )|(?<=July )|(?<=August )|(?<=September )"
                   r"|(?<=October )|(?<=November )|(?<=December ))([1-3]\d{3})\b(?![\d,.]\d)(?!\s(?:credits?|tonnes?|tons?|metres?|kilometres?|light|ly|units?|cr|jumps?|percent|%))")
_ORDINAL = re.compile(r"\b([1-9]|[12]\d|3[01])(st|nd|rd|th)\b")
_SYSTEM_CODE = re.compile(r"\b([A-Z]{2})-([A-Z]) ([A-Ha-h])(\d{1,2})(?:-(\d{1,4}))?\b")
_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen").split()
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_ORDINAL_WORDS = {1: "first", 2: "second", 3: "third", 5: "fifth", 8: "eighth", 9: "ninth", 12: "twelfth", 20: "twentieth", 30: "thirtieth"}

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


def _below_hundred(n):
    if n < 20:
        return _ONES[n]
    return _TENS[n // 10] + ("-" + _ONES[n % 10] if n % 10 else "")


def _year_words(year):
    """1994 = 'nineteen ninety-four', 2014 = 'twenty fourteen', 3309 = 'thirty-three oh nine', 2000 = 'two thousand', 3300 = 'thirty-three hundred'."""
    if year % 1000 == 0:
        return "%s thousand" % _ONES[year // 1000]
    high, low = divmod(year, 100)
    if 2000 <= year <= 2009:
        return "two thousand %s" % _ONES[low]
    if low == 0:
        return "%s hundred" % _below_hundred(high)
    if low < 10:
        return "%s oh %s" % (_below_hundred(high), _ONES[low])
    return "%s %s" % (_below_hundred(high), _below_hundred(low))


def _ordinal_words(match):
    n = int(match.group(1))
    if n in _ORDINAL_WORDS:
        return _ORDINAL_WORDS[n]
    if n < 20:
        return _ONES[n] + "th"
    tens, ones = n - n % 10, n % 10
    return _TENS[tens // 10][:-1] + "ieth" if not ones else _below_hundred(tens) + "-" + _ORDINAL_WORDS.get(ones, _ONES[ones] + "th")


def _system_code(match):
    first, single, mass, number, last = match.groups()
    spelled = lambda text: " ".join(text)
    out = "%s, %s, %s %s" % (spelled(first), single, mass.upper(), spelled(number))
    return out + (", %s" % spelled(last) if last else "")


def _spoken_decimal(match):
    return "%s point %s" % (match.group(1), " ".join(match.group(2)))


def prepare(text, voice_name=""):
    """The text as it should be handed to the voice. Safe on anything: a failure returns the text unchanged."""
    if not text:
        return text
    try:
        out = _SYSTEM_CODE.sub(_system_code, text)
        out = _YEAR.sub(lambda m: _year_words(int(m.group(1))), out)
        out = _ORDINAL.sub(_ordinal_words, out)
        out = _DECIMAL.sub(_spoken_decimal, out)
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
