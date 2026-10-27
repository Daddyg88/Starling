"""
WHAT SHE KNOWS - facts she answers exactly and never invents.

Everything lives in plain JSON files in config/knowledge/ so you can add to it yourself:
  capitals.json    countries and their capitals ("what is the capital of Germany")
  languages.json   greetings in other languages ("how do you say thank you in German")
  space.json, science.json, world.json, elite.json, tech.json
                   {"k": [[word, word], [word, word]], "a": "the answer"}  - "k" is a list of alternatives, each a list of words that must
                   ALL be in the question (plural 's' ignored). The entry with the most matching words wins.
  style.json       the little lead-ins she puts in front ("Easy one.") and how maths answers sound.
She also does sums (plus, minus, times, divided by, percent, square roots) and unit conversions in code, and only
answers a question like that when the numbers are there, so a chat sentence is never mistaken for one.

She only answers when sure. No match -> None, and the brain carries on (she says she doesn't know, or the optional AI takes it).
"""
import json
import math
import re

from core import paths
from core.logger import get_logger

log = get_logger("knowledge")

QUESTION_START = {"what", "whats", "who", "whos", "where", "wheres", "when", "whens", "which", "how", "why", "is", "are", "does", "do", "can",
                  "did", "was", "were", "name", "explain", "define", "describe", "tell", "give", "calculate", "work", "convert"}
LEADS = ("do you know ", "can you tell me ", "could you tell me ", "tell me ", "i was wondering ", "quick question ", "just wondering ",
         "i wonder ", "hey ", "ok ", "okay ", "so ", "right ", "um ", "erm ", "uh ")
SHORT_ANSWER_WORDS = 6


def stem(word):
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def words_of(text):
    return [stem(w) for w in re.findall(r"[a-z0-9]+", (text or "").lower().replace("'", ""))]


_ONES = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
         "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_NUMBER_WORDS = "|".join(list(_ONES) + list(_TENS) + ["hundred", "thousand", "million"])
_NUMWORD_ALL = re.compile(r"\b(?:%s)\b(?:[ -]+(?:%s)\b)*" % (_NUMBER_WORDS, _NUMBER_WORDS))


def _number_run(run):
    total, current = 0, 0
    for word in re.split(r"[ -]+", run):
        if word == "and":
            continue
        if word in _ONES:
            current += _ONES[word]
        elif word in _TENS:
            current += _TENS[word]
        elif word == "hundred":
            current = max(current, 1) * 100
        elif word == "thousand":
            total += max(current, 1) * 1000
            current = 0
        elif word == "million":
            total += max(current, 1) * 1000000
            current = 0
    return str(total + current)


def digits(text):
    """'twelve times seven' -> '12 times 7'."""
    return _NUMWORD_ALL.sub(lambda m: _number_run(m.group(0)), text)


def say_number(value, sig=6):
    if isinstance(value, float):
        if abs(value - round(value)) < 1e-9:
            value = int(round(value))
        else:
            value = float("%.*g" % (sig, value))
            if abs(value) >= 1000:
                value = round(value, 1)
    return "{:,}".format(value) if isinstance(value, int) and abs(value) >= 10000 else str(value)


# ---- maths ----
NUM = r"(-?\d+(?:\.\d+)?)"
CALC_LEAD = re.compile(r"^(?:what(?:s| is| are)?|whats|how much (?:is|are)|calculate|work out|compute|tell me|do you know|can you (?:tell me|work out|calculate))\b")
BINARY = re.compile(r"%s\s*(plus|minus|times|multiplied by|x|divided by|over|\+|-|\*|/|÷|take away|add|subtract|\^)\s*%s" % (NUM, NUM))
PERCENT = re.compile(r"%s\s*(?:percent|per cent|%%)\s*of\s*%s" % (NUM, NUM))
ROOT = re.compile(r"square root of %s" % NUM)
POWER = re.compile(r"%s\s*(squared|cubed)\b" % NUM)
HALF = re.compile(r"\b(half|double|twice|triple|a third|a quarter) (?:of )?%s" % NUM)
OPS = {"plus": "plus", "+": "plus", "add": "plus", "minus": "minus", "-": "minus", "take away": "minus", "subtract": "minus",
       "times": "times", "multiplied by": "times", "x": "times", "*": "times",
       "divided by": "divided by", "over": "divided by", "/": "divided by", "÷": "divided by", "^": "to the power of"}


def _num(text):
    value = float(text)
    return int(value) if value == int(value) and "." not in text else value


def maths(raw):
    """(sentence, None) or (None, 'zero') or None if this is not a sum."""
    text = digits((raw or "").lower().replace(",", ""))
    text = re.sub(r"\s+", " ", text.replace("what's", "what is").replace("whats", "what is")).strip(" ?.!")
    if not re.search(r"\d", text):
        return None
    has_lead = bool(CALC_LEAD.match(text)) or text.endswith(("equal", "equals", "=")) or " equal" in text
    if not has_lead and len(text.split()) > 4:
        return None
    text = re.sub(r"\s*(?:equals?|=)\s*$", "", text)
    found = PERCENT.search(text)
    if found:
        a, b = _num(found.group(1)), _num(found.group(2))
        return "%s percent of %s is %s" % (say_number(a), say_number(b), say_number(a * b / 100)), None
    found = ROOT.search(text)
    if found:
        a = _num(found.group(1))
        if a < 0:
            return None
        return "the square root of %s is %s" % (say_number(a), say_number(math.sqrt(a))), None
    found = POWER.search(text)
    if found:
        a = _num(found.group(1))
        n = 2 if found.group(2) == "squared" else 3
        return "%s %s is %s" % (say_number(a), found.group(2), say_number(a ** n)), None
    found = HALF.search(text)
    if found:
        factor = {"half": 0.5, "double": 2, "twice": 2, "triple": 3, "a third": 1 / 3, "a quarter": 0.25}[found.group(1)]
        a = _num(found.group(2))
        return "%s of %s is %s" % (found.group(1), say_number(a), say_number(a * factor)), None
    found = BINARY.search(text)
    if found:
        a, op, b = _num(found.group(1)), OPS.get(found.group(2)), _num(found.group(3))
        if op is None:
            return None
        if not has_lead and found.group(2) in ("-", "x", "over"):
            return None                      # "2-3 jumps", "x 5": not a sum without a clear question
        if op == "divided by" and b == 0:
            return None, "zero"
        value = {"plus": a + b, "minus": a - b, "times": a * b, "divided by": (a / b if b else 0),
                 "to the power of": (a ** b if abs(b) <= 10 and abs(a) <= 1000 else None)}[op]
        if value is None:
            return None
        return "%s %s %s is %s" % (say_number(a), op, say_number(b), say_number(value)), None
    return None


# ---- units ----
UNIT_ALIASES = {
    "celsius": "c", "centigrade": "c", "fahrenheit": "f", "kelvin": "k",
    "kilometre": "km", "kilometer": "km", "kilometres": "km", "kilometers": "km", "km": "km", "mile": "mi", "miles": "mi",
    "metre": "m", "meter": "m", "metres": "m", "meters": "m", "feet": "ft", "foot": "ft", "inch": "in", "inches": "in",
    "centimetre": "cm", "centimeter": "cm", "centimetres": "cm", "centimeters": "cm", "cm": "cm", "yard": "yd", "yards": "yd",
    "kilogram": "kg", "kilograms": "kg", "kilo": "kg", "kilos": "kg", "kg": "kg", "pound": "lb", "pounds": "lb", "lb": "lb", "lbs": "lb",
    "ounce": "oz", "ounces": "oz", "gram": "g", "grams": "g", "stone": "st",
    "litre": "l", "liter": "l", "litres": "l", "liters": "l", "gallon": "gal", "gallons": "gal", "pint": "pt", "pints": "pt",
    "light year": "ly", "light years": "ly", "lightyear": "ly", "lightyears": "ly", "ly": "ly",
}
UNIT_NAMES = {"c": "degrees Celsius", "f": "degrees Fahrenheit", "k": "kelvin", "km": "kilometres", "mi": "miles", "m": "metres",
              "ft": "feet", "in": "inches", "cm": "centimetres", "yd": "yards", "kg": "kilograms", "lb": "pounds", "oz": "ounces",
              "g": "grams", "st": "stone", "l": "litres", "gal": "gallons", "pt": "pints", "ly": "light years"}
TO_BASE = {"km": 1000.0, "mi": 1609.344, "m": 1.0, "ft": 0.3048, "in": 0.0254, "cm": 0.01, "yd": 0.9144, "ly": 9.4607e15,
           "kg": 1000.0, "lb": 453.59237, "oz": 28.349523, "g": 1.0, "st": 6350.29318,
           "l": 1.0, "gal": 3.785411784, "pt": 0.568261}
FAMILY = {"km": "len", "mi": "len", "m": "len", "ft": "len", "in": "len", "cm": "len", "yd": "len", "ly": "len",
          "kg": "mass", "lb": "mass", "oz": "mass", "g": "mass", "st": "mass", "l": "vol", "gal": "vol", "pt": "vol"}
_UNIT_WORDS = "|".join(sorted((re.escape(u) for u in UNIT_ALIASES), key=len, reverse=True))
CONVERT = re.compile(r"%s\s*(?:degrees? )?(%s)\b\s*(?:to|in|into|is how many|equals? how many|as)\s*(?:degrees? )?(%s)\b" % (NUM, _UNIT_WORDS, _UNIT_WORDS))
HOWMANY = re.compile(r"how many (%s) (?:are )?(?:there )?in %s\s*(?:degrees? )?(%s)\b" % (_UNIT_WORDS, NUM, _UNIT_WORDS))


def _temperature(value, src, dst):
    kelvin = {"c": value + 273.15, "f": (value - 32) * 5 / 9 + 273.15, "k": value}[src]
    return {"c": kelvin - 273.15, "f": (kelvin - 273.15) * 9 / 5 + 32, "k": kelvin}[dst]


def convert(raw):
    """'convert 20 celsius to fahrenheit' -> '20 degrees Celsius is 68 degrees Fahrenheit', or None."""
    text = digits((raw or "").lower().replace(",", ""))
    text = re.sub(r"\s+", " ", text).strip(" ?.!")
    value = src = dst = None
    found = CONVERT.search(text)
    if found:
        value, src, dst = _num(found.group(1)), UNIT_ALIASES[found.group(2)], UNIT_ALIASES[found.group(3)]
    else:
        found = HOWMANY.search(text)
        if found:
            dst, value, src = UNIT_ALIASES[found.group(1)], _num(found.group(2)), UNIT_ALIASES[found.group(3)]
    if value is None or src == dst:
        return None
    if src in ("c", "f", "k") and dst in ("c", "f", "k"):
        result = _temperature(value, src, dst)
    elif src in FAMILY and dst in FAMILY and FAMILY[src] == FAMILY[dst]:
        result = value * TO_BASE[src] / TO_BASE[dst]
    else:
        return None
    return "%s %s is %s %s" % (say_number(value), UNIT_NAMES[src], say_number(result, 4), UNIT_NAMES[dst])


# ---- the library ----
class Knowledge:
    def __init__(self, folder=None):
        folder = folder or (paths.CONFIG_DIR / "knowledge")
        self.entries = []                   # [(alternatives as sets of stems, answer)]
        self.capitals, self.aliases, self.by_city = {}, {}, {}
        self.languages, self.lang_words, self.lang_answers = {}, [], []
        self.style = {}
        self.capital_answers = []
        if folder.is_dir():
            for path in sorted(folder.glob("*.json")):
                try:
                    with open(path, "r", encoding="utf-8") as handle:
                        data = json.load(handle)
                except Exception:
                    log.exception("Could not read %s", path)
                    continue
                self._add(data)
        self._place_names = sorted(list(self.capitals) + list(self.aliases), key=lambda n: -len(n))

    def _add(self, data):
        for entry in data.get("entries", []):
            alternatives = [frozenset(words_of(" ".join(alt))) for alt in entry.get("k", [])]
            if alternatives and entry.get("a"):
                self.entries.append((alternatives, entry["a"]))
        if "capitals" in data:
            self.capitals = {k.lower(): (k, v) for k, v in data["capitals"].items()}
            self.aliases = {k.lower(): v.lower() for k, v in data.get("aliases", {}).items()}
            self.capital_answers = data.get("answers", [])
            for key, (place, city) in self.capitals.items():
                self.by_city.setdefault(city.split(",")[0].lower(), place)
        if "languages" in data:
            self.languages = {k.lower(): v for k, v in data["languages"].items()}
            self.lang_words = data.get("words", [])
            self.lang_answers = data.get("answers", [])
        if "leads" in data:
            self.style = data

    # ---- asking ----
    def looks_like_question(self, tidy):
        """'question' (starts like one), 'short' (a few words: 'capital of france'), or None."""
        words = tidy.split()
        for lead in LEADS:
            if tidy.startswith(lead):
                tidy = tidy[len(lead):]
                words = tidy.split()
        if not words:
            return None
        if words[0] in QUESTION_START:
            return "question"
        return "short" if len(words) <= SHORT_ANSWER_WORDS else None

    def lookup(self, tidy):
        """(kind, answer text) or None. kind: 'fact', 'capital', 'language'."""
        shape = self.looks_like_question(tidy)
        if shape is None and not re.search(r"capital of (?:which|what) (?:country|nation)", tidy):
            return None
        found = self._capital(tidy)
        if found:
            return "capital", found
        found = self._language(tidy)
        if found:
            return "language", found
        have = set(words_of(tidy))
        best, best_size = None, 0
        for alternatives, answer in self.entries:
            for alt in alternatives:
                if len(alt) > best_size and alt <= have and (shape == "question" or len(alt) >= 2):
                    best, best_size = answer, len(alt)
        return ("fact", best) if best else None

    def _find_place(self, tidy):
        padded = " " + tidy + " "
        for name in self._place_names:
            if (" %s " % name) in padded:
                return self.aliases.get(name, name)
        return None

    def _capital(self, tidy, rng=None):
        if "capital" not in tidy:
            return None
        key = self._find_place(tidy)
        if key and key in self.capitals:
            place, city = self.capitals[key]
            return ("C", place, city)
        padded = " " + tidy + " "
        for city in sorted(self.by_city, key=len, reverse=True):
            if (" %s " % city) in padded and re.search(r"\b(?:country|which|what|where)\b", tidy):
                place = self.by_city[city]
                return ("R", place, city.title())
        return None

    def _language(self, tidy):
        if not self.languages:
            return None
        lang = next((name for name in self.languages if re.search(r"\b%s\b" % name, tidy)), None)
        if lang is None:
            return None
        synonyms = {"hi": "hello", "hey": "hello", "hallo": "hello", "thanks": "thank you", "cheers": "thank you", "bye": "goodbye",
                    "farewell": "goodbye", "see you": "goodbye", "pardon": "sorry", "excuse me": "sorry", "goodnight": "good night"}
        word = None
        for candidate in sorted(self.lang_words + list(synonyms), key=len, reverse=True):
            if re.search(r"\b%s\b" % re.escape(candidate), tidy):
                word = synonyms.get(candidate, candidate)
                break
        if word is None or word not in self.lang_words:
            return None
        spoken = self.languages[lang][self.lang_words.index(word)]
        return (lang.title(), word, spoken)
