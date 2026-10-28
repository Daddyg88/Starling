"""Ship facts she knows by heart (0.77.0): cost, jump range, hardpoints, cargo... for every ship in config/ships_specs.json.

Everything is answered offline. The numbers come from the Elite Dangerous wiki (see tools/build_ship_specs.py).
"""
import difflib
import json
import random
import re

from core import paths
from core.logger import get_logger
from personality.lookup import norm_ship

log = get_logger("ships_info")

SPECS_FILE = paths.CONFIG_DIR / "ships_specs.json"
ANSWERS_FILE = paths.CONFIG_DIR / "ship_answers.json"

# Words that are not enough on their own to name a ship.
GENERIC = {"explorer", "scout", "heavy", "transporter", "mark", "ship", "type", "imperial", "federal", "alliance", "panther",
           "liner", "assault", "gunship", "ships", "the", "with", "that", "this", "what", "which", "much", "does", "have", "many"}
# Ship names that are also animals or ordinary words: a plain "how fast is a dolphin" needs a hint that it is the ship.
ANIMALS = {"anaconda", "adder", "eagle", "python", "viper", "mamba", "orca", "dolphin", "asp", "corsair", "kestrel", "vulture",
           "lynx", "cobra", "sidewinder", "krait", "diamondback", "beluga", "panther", "hauler", "keelback", "mandalay",
           "caspian", "cutter", "courier", "clipper", "prospector", "defender", "phantom"}

# stat -> words that ask for it, in the order they are tried.
STATS = [
    ("insurance", r"\b(insurance|insured|re ?buy)\b"),
    ("fuel", r"\bfuel\b"),
    ("cargo", r"\b(cargo|carry|carries|hold|holds|tonnes? of cargo|capacity)\b"),
    ("jump", r"\b(jump|jumps|how far|range)\b"),
    ("utility", r"\butilit(y|ies)\b"),
    ("hardpoints", r"\b(hard ?points?|weapons?|guns?|armed|gun slots)\b"),
    ("internal", r"\b(internals?|compartments?|slots|optional)\b"),
    ("boost", r"\bboosts?\b"),
    ("speed", r"\b(speed|how fast|fast)\b"),
    ("mass", r"\b(mass|weigh|weighs|weight|heavy)\b"),
    ("armour", r"\b(armou?r|hardness)\b"),
    ("shields", r"\bshields?\b"),
    ("manufacturer", r"\b(who (makes|made|builds|built|manufactures)|manufacturer|maker|built by|made by)\b"),
    ("pad", r"\b(landing pad|pad size|pad)\b"),
    ("seats", r"\b(seats?|crew|multi ?crew|how many (people|pilots))\b"),
    ("fighter", r"\b(fighter|hangar|hanger)\b"),
    ("manoeuvre", r"\b(manoeuvr\w*|maneuver\w*|agile|agility|nimble)\b"),
    ("heat", r"\bheat\b"),
    ("sco", r"\b(sco|overcharge|supercruise overcharge)\b"),
    ("year", r"\b(what year|which year|when (was|did)|introduced|released|come out)\b"),
    ("dimensions", r"\b(dimensions?|how (big|long|wide|large)|length)\b"),
    ("role", r"\b(role|what (kind|type|sort|class) of ship|used for|good for|is it for)\b"),
    ("cost", r"\b(cost|costs|price|priced|expensive|cheap|afford|worth|how much)\b"),
]
GENERIC_STATS = {"speed", "mass", "armour", "shields", "fuel", "manufacturer", "heat", "role", "year", "dimensions", "manoeuvre", "boost", "seats"}

SUMMARY = re.compile(r"\b(tell me about|what is|whats|what s|what are|describe|stats|specs|overview|information on|info on|facts about|about)\b")
SHIP_HINT = re.compile(r"\b(ship|ships|elite|flying|fly|pilot|dangerous)\b")
FOLLOW = re.compile(r"^and\b|\b(it|its|that one|this one|the same)\b")

COUNT = re.compile(r"\bhow many (different )?(ships|vessels)\b")
SUPER = re.compile(r"\b(which|what|whats|what s|who)\b.*\b(ship|ships|vessel)\b.*\b(biggest|largest|most|highest|best|longest|greatest|"
                   r"fastest|quickest|cheapest|lowest|least|smallest|lightest|heaviest|strongest|toughest)\b"
                   r"|\b(biggest|largest|fastest|cheapest|longest|heaviest|strongest|most expensive|lightest)\b.*\bship\b")

SIZES = ("small", "medium", "large", "huge")


def number_of(text):
    """The first number in '9.66 ly (default)' / '1,989,461 CR' as a float, or None."""
    found = re.search(r"\d[\d,]*\.?\d*", text or "")
    if not found:
        return None
    try:
        return float(found.group(0).replace(",", ""))
    except ValueError:
        return None


def say_number(value, places=1):
    """9.66 -> '9.7', 470.0 -> '470'."""
    value = round(float(value), places)
    return ("%d" % value) if value == int(value) else ("%.*f" % (places, value)).rstrip("0").rstrip(".")


def say_credits(value):
    """128965694 -> 'about 129 million credits', 44800 -> '44,800 credits'."""
    if value is None:
        return None
    if value >= 1e9:
        return "about %s billion credits" % say_number(value / 1e9, 2)
    if value >= 1e6:
        return "about %s million credits" % say_number(value / 1e6, 2 if value < 1e7 else 1)
    return "{:,} credits".format(int(value))


def say_range(text):
    """'30.79-60~ ly (upgraded)' -> 'about 30.8 to 60'."""
    found = re.search(r"(\d+\.?\d*)\s*-\s*(\d+\.?\d*)", text or "")
    if found:
        return "about %s to %s" % (say_number(float(found.group(1))), say_number(float(found.group(2))))
    number = number_of(text)
    return None if number is None else say_number(number)


def pick_pair(entries):
    """(stock, best) from ['9.66 ly (default)', '41.45 ly (upgraded)']; either can be None."""
    entries = [e for e in (entries or []) if e]
    if not entries:
        return None, None
    stock = next((e for e in entries if "default" in e.lower()), entries[0])
    best = next((e for e in reversed(entries) if "upgraded" in e.lower() or "max" in e.lower()), entries[-1])
    return stock, best


def counted(entries):
    """['2× Small Hardpoints'] -> [(2, 'Small Hardpoints')]"""
    out = []
    for entry in entries or []:
        found = re.match(r"\s*(\d+)\s*[×xX]\s*(.+)", entry)
        if found:
            out.append((int(found.group(1)), found.group(2).strip()))
    return out


def join_words(parts):
    parts = list(parts)
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def values_for(ship):
    """Everything a template could use, spoken the way she says it. Missing ones are simply left out."""
    v = {"ship": ship["name"]}

    def put(key, value):
        if value not in (None, ""):
            v[key] = value
    put("manufacturer", ship.get("manufacturer"))
    put("role", (ship.get("role") or "").lower() or None)
    put("pad", (ship.get("pad") or "").lower() or None)
    put("mass", say_number(number_of(ship.get("mass"))) if number_of(ship.get("mass")) is not None else None)
    put("armour", ship.get("armour"))
    put("hardness", ship.get("hardness"))
    shield = number_of(ship.get("shields"))
    put("shields", say_number(shield) if shield is not None else None)
    fuel = number_of(ship.get("fuel"))
    put("fuel", say_number(fuel) if fuel is not None else None)
    put("manoeuvrability", ship.get("manoeuvrability"))
    put("heat", ship.get("heat"))
    put("seats", (ship.get("seats") or "").replace("-", " to ") or None)
    put("cost", say_credits(number_of(ship.get("cost"))))
    put("insurance", say_credits(number_of(ship.get("insurance"))))
    year = re.match(r"\s*(\d{4})", ship.get("years") or "")
    put("years_start", year.group(1) if year else None)
    dims = ship.get("dimensions")
    if dims:
        put("dimensions", re.sub(r"\s*x\s*", " by ", re.sub(r"(\d)m\b", r"\1 metres", dims), flags=re.I))
    if ship.get("multicrew"):
        v["multicrew_sentence"] = "It supports multicrew." if ship["multicrew"].lower().startswith("y") else "It doesn't support multicrew."
    if ship.get("fighter_bay"):
        yes = ship["fighter_bay"].lower().startswith("y")
        v["fighter_sentence"] = ("The %s has a fighter hangar." if yes else "The %s has no fighter hangar.") % ship["name"]
    if ship.get("sco"):
        yes = ship["sco"].lower().startswith("y")
        v["sco_sentence"] = ("The %s has a supercruise overcharge drive." if yes else "The %s doesn't have a supercruise overcharge drive.") % ship["name"]
    for key, field, speaker in (("jump", "jump", say_range), ("speed", "speed", None), ("boost", "boost", None), ("cargo", "cargo", None)):
        stock, best = pick_pair(ship.get(field))
        for tag, text in (("stock", stock), ("best", best)):
            if text is None:
                continue
            if speaker:
                spoken = speaker(text)
            else:
                number = number_of(text)
                spoken = None if number is None else say_number(number)
            if spoken:
                v["%s_%s" % (key, tag)] = spoken
                if key == "cargo" and tag == "best":
                    v["cargo_max"] = spoken
    weapons, utility, breakdown = 0, 0, []
    for amount, label in counted(ship.get("hardpoints")):
        if "utility" in label.lower():
            utility += amount
            continue
        weapons += amount
        size = next((s for s in SIZES if label.lower().startswith(s)), label.lower())
        breakdown.append("%d %s" % (amount, size))
    if weapons or utility:
        v["weapons"] = str(weapons)
        v["utility"] = str(utility)
        v["weapon_breakdown"] = join_words(breakdown) if breakdown else "none"
    slots, parts = 0, []
    for amount, label in counted(ship.get("internal")):
        slots += amount
        match = re.search(r"class\s*(\d+)", label, re.I)
        parts.append("%d class %s" % (amount, match.group(1)) if match else "%d %s" % (amount, label.lower()))
    if parts:
        v["internal_count"] = str(slots)
        v["internal_breakdown"] = join_words(parts)
        extra = [("%d %s" % (a, l.lower())) for a, l in counted(ship.get("reserved"))]
        v["reserved_sentence"] = (" Plus reserved: %s." % join_words(extra)) if extra else ""
    return v


def metric(ship, stat):
    """A number to compare ships by (None when the ship has none)."""
    if stat == "cost":
        return number_of(ship.get("cost"))
    if stat == "cargo":
        return number_of(pick_pair(ship.get("cargo"))[1])
    if stat == "jump":
        entry = pick_pair(ship.get("jump"))[1]
        found = re.search(r"(\d+\.?\d*)\s*-\s*(\d+\.?\d*)", entry or "")
        return float(found.group(2)) if found else number_of(entry)
    if stat == "speed":
        return number_of(pick_pair(ship.get("speed"))[1])
    if stat == "boost":
        return number_of(pick_pair(ship.get("boost"))[1])
    if stat == "mass":
        return number_of(ship.get("mass"))
    if stat == "armour":
        return number_of(ship.get("armour"))
    if stat == "shields":
        return number_of(ship.get("shields"))
    if stat == "hardpoints":
        return float(sum(a for a, l in counted(ship.get("hardpoints")) if "utility" not in l.lower()))
    if stat == "utility":
        return float(sum(a for a, l in counted(ship.get("hardpoints")) if "utility" in l.lower()))
    if stat == "internal":
        return float(sum(a for a, _l in counted(ship.get("internal"))))
    if stat == "fuel":
        return number_of(ship.get("fuel"))
    if stat == "manoeuvre":
        return number_of(ship.get("manoeuvrability"))
    if stat == "insurance":
        return number_of(ship.get("insurance"))
    return None


def spoken_metric(stat, number):
    if stat in ("cost", "insurance"):
        return say_credits(number)
    unit = {"cargo": " tonnes", "jump": " light years", "speed": " metres per second", "boost": " metres per second",
            "mass": " tonnes", "shields": " megajoules", "fuel": " tonnes", "hardpoints": " weapon hardpoints",
            "utility": " utility mounts", "internal": " internal slots"}.get(stat, "")
    return say_number(number) + unit


SUPER_WORDS = [  # (pattern, stat, largest first?)
    (r"\bmost expensive|priciest\b", "cost", True), (r"\b(cheapest|least expensive)\b", "cost", False),
    (r"\b(cargo|carry|carries|hold)\b", "cargo", True), (r"\b(jump|range|how far)\b", "jump", True),
    (r"\b(fastest|quickest|top speed)\b", "speed", True), (r"\bboost", "boost", True),
    (r"\b(hard ?points?|weapons?|guns)\b", "hardpoints", True), (r"\butility\b", "utility", True),
    (r"\b(internals?|compartments?|slots)\b", "internal", True), (r"\bshields?\b", "shields", True),
    (r"\b(armou?r|toughest|strongest)\b", "armour", True), (r"\b(heaviest|mass)\b", "mass", True),
    (r"\blightest\b", "mass", False), (r"\bfuel\b", "fuel", True),
]


ROMAN = {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5", "VI": "6"}


def spoken_marks(text):
    """'Cobra Mk V' -> 'Cobra Mark 5', so she says it properly."""
    return re.sub(r"\bMk (VI|IV|V|III|II|I)\b", lambda m: "Mark " + ROMAN[m.group(1)], text).replace("Mk ", "Mark ")


class ShipInfo:
    def __init__(self, specs_file=None, answers_file=None, rng=None):
        self.rng = rng or random.Random()
        self.ships = []
        self.lines = {}
        self.heard_as = {}
        try:
            with open(specs_file or SPECS_FILE, encoding="utf-8") as handle:
                self.ships = json.load(handle).get("ships", [])
            with open(answers_file or ANSWERS_FILE, encoding="utf-8") as handle:
                data = json.load(handle)
            self.heard_as = data.pop("heard_as", {})
            self.lines = {k: v for k, v in data.items() if not k.startswith("_")}
        except Exception:
            log.exception("Could not load the ship notes; ship questions will go to the wiki instead")
            self.ships = []
        self.by_name = {norm_ship(s["name"]): s for s in self.ships}
        self.aliases = self._build_aliases()
        self.vocab = sorted({w for n in self.by_name for w in n.split() if len(w) >= 5 and w not in GENERIC})

    def available(self):
        return bool(self.ships)

    def names(self):
        return [s["name"] for s in self.ships]

    def _build_aliases(self):
        """Short ways of saying a ship: 'type 9', 'prospector'. Each maps to the ships it could mean."""
        table = {}
        for key in self.by_name:
            words = key.split()
            options = set()
            if words[0] == "type" and len(words) > 2:
                options.add("type %s" % words[1])
            for word in words:
                if word not in GENERIC and len(word) >= 4 and word != "mark" and not word.isdigit():
                    options.add(word)
            for option in options:
                table.setdefault(option, [])
                if key not in table[option]:
                    table[option].append(key)
        for option, keys in table.items():     # a bare 'Anaconda' means the Anaconda, not the Mark 2
            if option in self.by_name:
                table[option] = [option]
        return table

    # ---- finding the ship ----
    def _fix_heard(self, text):
        for wrong, right in self.heard_as.items():
            text = re.sub(r"\b%s\b" % re.escape(wrong), right, text)
        return text

    def find(self, tidy, loose=False):
        """(ship, None) when sure, (None, [ships]) when it could be several, (None, None) when no ship is named."""
        text = " %s " % norm_ship(tidy)
        for key in sorted(self.by_name, key=len, reverse=True):
            if (" %s " % key) in text:
                return self.by_name[key], None
        if not loose:
            return None, None
        text = " %s " % self._fix_heard(text.strip())
        for key in sorted(self.by_name, key=len, reverse=True):
            if (" %s " % key) in text:
                return self.by_name[key], None
        for option in sorted(self.aliases, key=len, reverse=True):
            if (" %s " % option) in text:
                keys = self.aliases[option]
                if len(keys) == 1:
                    return self.by_name[keys[0]], None
                return None, [self.by_name[k] for k in keys]
        for word in text.split():
            if len(word) >= 5 and word not in GENERIC and not any(re.search(p, word) for _s, p in STATS):
                close = difflib.get_close_matches(word, self.vocab, n=1, cutoff=0.8)
                if close:
                    keys = self.aliases.get(close[0], [])
                    if len(keys) == 1:
                        return self.by_name[keys[0]], None
                    if keys:
                        return None, [self.by_name[k] for k in keys]
        return None, None

    def stat_of(self, tidy):
        for stat, pattern in STATS:
            if re.search(pattern, tidy):
                return stat
        return None

    # ---- answering ----
    def _fill(self, group, values):
        options = [t for t in self.lines.get(group, [])]
        self.rng.shuffle(options)
        for template in options:
            try:
                return template.format(**values)
            except (KeyError, IndexError):
                continue
        return None

    def answer(self, tidy, current=None, last=None):
        """(sentence, ship name or None) or None when this isn't a ship question."""
        found = self._answer(tidy, current, last)
        if found and found[0]:
            return spoken_marks(found[0]), found[1]
        return None

    def _answer(self, tidy, current=None, last=None):
        if not self.ships:
            return None
        tidy = tidy.lower()
        if COUNT.search(tidy) and re.search(r"\b(elite|game|there|fly|know)\b", tidy):
            text = self._fill("count", {"count": len(self.ships)})
            return (text, None) if text else None
        if SUPER.search(tidy):
            found = self._superlative(tidy)
            if found:
                return found, None
        stat = self.stat_of(tidy)
        summary = bool(SUMMARY.search(tidy))
        if stat is None and not summary:
            return None
        hint = bool(SHIP_HINT.search(tidy))
        ship, several = self.find(tidy, loose=True)
        if ship is None and several is None:
            mine = re.search(r"\b(my|this|current|our) (ship|ride|vessel)\b|\bi m (flying|in)\b|\bi am (flying|in)\b", tidy)
            if mine:
                if current is None:
                    return (self._fill("no_my_ship", {}), None) if stat else None
                ship = self.by_name.get(norm_ship(current))
                hint = True
            elif last is not None and FOLLOW.search(tidy) and stat is not None:
                ship = self.by_name.get(norm_ship(last))
                hint = True
        if several:
            if stat is None and not hint:
                return None
            names = [s["name"] for s in several]
            return "Which one, the %s?" % " or the ".join([", the ".join(names[:-1]), names[-1]] if len(names) > 2 else names), None
        if ship is None:
            return None
        key = norm_ship(ship["name"])
        if key.split()[0] in ANIMALS and len(key.split()) == 1 and not hint and last is None:
            if stat is None or stat in GENERIC_STATS:
                return None                                  # probably the animal
        values = values_for(ship)
        if stat is None or (summary and stat in ("role",) and not re.search(r"\bgood for|used for|role\b", tidy)):
            text = self._fill("summary", values)
            return (text, ship["name"]) if text else None
        group = {"cost": "cost_insurance" if re.search(r"insur|rebuy|re buy", tidy) else "cost"}.get(stat, stat)
        text = self._fill(group, values) or self._fill("unknown", values)
        return (text, ship["name"]) if text else None

    def _superlative(self, tidy):
        for pattern, stat, largest in SUPER_WORDS:
            if re.search(pattern, tidy):
                break
        else:
            return None
        if re.search(r"\b(smallest|lowest|least)\b", tidy) and stat != "cost":
            largest = False
        scored = [(metric(s, stat), s["name"]) for s in self.ships]
        scored = [(m, n) for m, n in scored if m is not None]
        if len(scored) < 3:
            return None
        scored.sort(key=lambda item: item[0], reverse=largest)
        top = scored[:3]
        names = [n for _m, n in top]
        values = [spoken_metric(stat, m) for m, _n in top]
        if stat == "cost":
            group = "super_cost_max" if largest else "super_cost_min"
        else:
            group = "super_max" if largest else "super_min"
        text = self._fill(group, {"names": names, "values": values})
        return text
