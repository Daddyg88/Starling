"""
What is worth mining. One small table, easy to edit.

Tiers:  top  = your ten favourites (she gets properly excited). Choose them on the dashboard: Mining page.
        good = solid money (she is pleased)
        low  = everything else (she keeps quiet about it)

The names are the game's own names in lower case, with no spaces ("lowtemperaturediamond").
Tiers are a rule of thumb from the mining community (core mining and laser mining guides); prices move every week,
so ask her "where should I sell this" for real, current prices.
"""
import re

# The ten minerals she gets EXCITED about. You choose them on the dashboard (Mining page); these are the starting ten.
DEFAULT_FAVOURITES = ["platinum", "painite", "opal", "lowtemperaturediamond", "monazite", "musgravite",
                      "serendibite", "grandidierite", "alexandrite", "rhodplumsite"]
FAVOURITE_BOXES = 10
# Solid money: she is pleased but not excited. (Gold and silver are deliberately NOT here: she ignores them.)
GOOD = {"osmium", "palladium", "bromellite", "benitoite"}

_settings = None


def bind(settings):
    """Let the dashboard's ten boxes (settings mining.fav1 ... mining.fav10) decide what she gets excited about."""
    global _settings
    _settings = settings


def option(name, default=None):
    """A mining setting (settings.json: "mining" > name). Safe before the settings are bound."""
    if _settings is None:
        return default
    try:
        value = _settings.get("mining." + name, default)
    except Exception:
        return default
    return default if value is None else value


def favourites():
    """The set of minerals (game names) she is excited about right now."""
    if _settings is None:
        return set(DEFAULT_FAVOURITES)
    chosen = set()
    for number in range(1, FAVOURITE_BOXES + 1):
        try:
            value = _settings.get("mining.fav%d" % number, None)
        except Exception:
            value = None
        if value:
            chosen.add(normal(value))
    return chosen

# The name Ardent (the price service) uses, when it is not just the spoken name in lower case.
SPOKEN_NAMES = {
    "platinum": "Platinum", "painite": "Painite", "lowtemperaturediamond": "Low Temperature Diamonds",
    "opal": "Void Opals", "monazite": "Monazite", "musgravite": "Musgravite", "serendibite": "Serendibite",
    "grandidierite": "Grandidierite", "alexandrite": "Alexandrite", "rhodplumsite": "Rhodplumsite",
    "osmium": "Osmium", "palladium": "Palladium", "gold": "Gold", "bromellite": "Bromellite",
    "benitoite": "Benitoite", "silver": "Silver", "cobalt": "Cobalt", "bertrandite": "Bertrandite",
    "indite": "Indite", "gallite": "Gallite", "uraninite": "Uraninite", "praseodymium": "Praseodymium",
    "samarium": "Samarium", "lithium": "Lithium", "tritium": "Tritium", "water": "Water",
}

# Things you can say, turned into the game's name.
ALIASES = {
    "ltd": "lowtemperaturediamond", "ltds": "lowtemperaturediamond",
    "low temperature diamond": "lowtemperaturediamond", "low temperature diamonds": "lowtemperaturediamond",
    "low temp diamond": "lowtemperaturediamond", "low temp diamonds": "lowtemperaturediamond",
    "void opal": "opal", "void opals": "opal", "opals": "opal",
    "monazite": "monazite", "musgravite": "musgravite", "serendibite": "serendibite",
    "grandidierite": "grandidierite", "alexandrite": "alexandrite", "rhodplumsite": "rhodplumsite",
    "platinum": "platinum", "painite": "painite", "osmium": "osmium", "palladium": "palladium",
    "gold": "gold", "bromellite": "bromellite", "benitoite": "benitoite", "silver": "silver",
    "tritium": "tritium", "cobalt": "cobalt",
}


def normal(name):
    """'Low Temperature Diamonds' / '$lowtemperaturediamond_name;' -> 'lowtemperaturediamond'. Never fails."""
    text = str(name or "").lower().strip()
    text = re.sub(r"[$;]|_name", "", text)
    text = re.sub(r"[^a-z]", "", text)
    if text in ("lowtemperaturediamonds",):
        text = "lowtemperaturediamond"
    if text in ("voidopal", "voidopals", "opals"):
        text = "opal"
    return text


def tier(name):
    key = normal(name)
    if key in favourites():
        return "top"
    if key in GOOD:
        return "good"
    return "low"


def spoken(name, localised=None):
    """The name she says out loud."""
    if localised:
        return str(localised).strip()
    key = normal(name)
    return SPOKEN_NAMES.get(key) or str(name or "").strip().title() or "something"


def from_speech(text):
    """Find a mineral in a sentence ('where do I sell the void opals'). Returns the game name or None."""
    tidy = " " + re.sub(r"[^a-z ]", " ", str(text or "").lower()) + " "
    tidy = re.sub(r"\s+", " ", tidy)
    for alias in sorted(ALIASES, key=len, reverse=True):          # longest first: "void opals" before "opals"
        if " " + alias + " " in tidy:
            return ALIASES[alias]
    return None
