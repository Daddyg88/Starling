"""
Exobiology bookkeeping: which sample you are on, what a finished species is worth,
and how much unsold exobiology data you are carrying.

Facts about the game this relies on (seen in your own debug_session.txt):
  * The journal's ScanOrganic event says "Log" for the 1st sample, "Sample" for the
    2nd AND the 3rd, and "Analyse" straight after the 3rd. So we count the samples ourselves.
  * The game does NOT tell us what a species is worth until you SELL it. So:
      - prices come from config/exobiology_values.json (approximate), and
      - every time you sell, the REAL price of each species is learned and saved
        (data/exobiology_learned.json), so later estimates are exact.
  * First footfall: the Scan event of a body says "WasFootfalled": false if nobody has
    stood on it yet. Then the data pays a bonus (5 x, set in the values file).
    If STARLING never saw that body's scan, she does not claim a bonus.
"""

import json
import os
import random
from pathlib import Path

from core.logger import get_logger

log = get_logger("exobiology")

DEFAULT_MULTIPLIER = 5
MAX_REMEMBERED_BODIES = 600
TOP_N = 10                       # "one of the ten most valuable species"


def spoken_credits(amount):
    """8418000 -> '8.4 million', 426200 -> '426 thousand', 950 -> '950'. Easy to say aloud."""
    amount = int(round(amount or 0))
    if amount >= 1_000_000_000:          # the game counts a thousand million as one billion
        return "%s billion" % ("%.1f" % (amount / 1_000_000_000.0)).rstrip("0").rstrip(".")
    if amount >= 1_000_000:
        value = round(amount / 1_000_000.0, 1)
        text = ("%.1f" % value).rstrip("0").rstrip(".")
        return "%s million" % text
    if amount >= 1000:
        return "%d thousand" % int(round(amount / 1000.0))
    return str(amount)


def spoken_range(low, high):
    """(1000000, 19000000) -> '1 to 19 million'; (800000, 19000000) -> '800 thousand to 19 million'. One number when they are close."""
    low, high = int(round(low or 0)), int(round(high or 0))
    if high <= 0:
        return spoken_credits(low)
    if low <= 0 or high <= low * 1.15:
        return spoken_credits((low + high) / 2.0 if low else high)
    a, b = spoken_credits(low), spoken_credits(high)
    wa, wb = a.split(" ", 1), b.split(" ", 1)
    if len(wa) == 2 and len(wb) == 2 and wa[1] == wb[1]:
        return "%s to %s" % (wa[0], b)                 # same unit: "1 to 19 million"
    return "%s to %s" % (a, b)


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        log.error("Could not read %s: %s", path, error)
        return {}


def _write_json(path, data):
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=1)
        os.replace(temp, path)
    except OSError:
        log.warning("Could not save %s", path, exc_info=True)


PLANET_WORDS = {"rocky": "rocky worlds", "highmetalcontent": "high metal content worlds", "rockyice": "rocky ice worlds",
                "icy": "icy worlds", "metalrich": "metal rich worlds"}
AIR_WORDS = {"carbondioxide": "carbon dioxide", "carbondioxiderich": "carbon dioxide", "sulphurdioxide": "sulphur dioxide",
             "oxygen": "oxygen", "ammonia": "ammonia", "helium": "helium", "argon": "argon", "argonrich": "argon",
             "water": "water vapour", "waterrich": "water vapour", "nitrogen": "nitrogen", "methane": "methane",
             "methanerich": "methane", "neon": "neon", "neonrich": "neon"}


def _join(words):
    words = list(dict.fromkeys(words))
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " or " + words[-1]


class BioInfo:
    """Short, checked descriptions of what she has just sampled (config/bio_info.json), plus facts worked out from the habitat rules
    (config/bio_rules.json), the prices and the sampling distances. Says nothing if she has none.

    She never repeats a fact about a species until she has told you all of them (the facts for each species are used up in a
    shuffled order and then start again), so a long trip through the same species keeps sounding fresh."""

    def __init__(self, path=None, rng=None, rules_path=None):
        data = _read_json(path) if path else {}
        self.genus = {str(k).lower(): [str(t) for t in v if t] for k, v in (data.get("genus") or {}).items()
                      if isinstance(v, list)}
        self.species = {str(k).lower(): str(v) for k, v in (data.get("species") or {}).items() if v}
        self.rules = {}
        if rules_path:
            for entry in ((_read_json(rules_path).get("species")) or []):
                if isinstance(entry, dict) and entry.get("n"):
                    self.rules[str(entry["n"]).lower()] = entry
        self.rng = rng or random.Random()
        self._last = {}
        self._left = {}              # species -> facts not yet told in this round

    def habitat_facts(self, species, values=None, distances=None, genus=""):
        """Sentences worked out from the checked habitat rules, the price list and the sampling distances."""
        rule = self.rules.get(str(species or "").lower())
        if not rule:
            return []
        facts = []
        planets = [PLANET_WORDS[p] for p in rule.get("p", []) if p in PLANET_WORDS]
        air = [AIR_WORDS[a] for a in rule.get("a", []) if a in AIR_WORDS]
        if rule.get("a") == ["none"]:
            facts.append("It grows on %s with no atmosphere at all." % _join(planets) if planets else "It grows with no atmosphere at all.")
        elif planets and air:
            where = "It is found on %s" % _join(planets)
            facts.append(where + (" with %s in the air." % _join(air) if len(set(air)) <= 3 else ", under several kinds of atmosphere."))
        elif planets:
            facts.append("It is found on %s." % _join(planets))
        if rule.get("gmax"):
            facts.append("It only grows where the gravity is no more than %g g." % rule["gmax"])
        tmin, tmax = rule.get("tmin"), rule.get("tmax")
        if tmin and tmax:
            facts.append("It likes a surface between %d and %d kelvin." % (tmin, tmax))
        elif tmin:
            facts.append("It needs a surface hotter than %d kelvin." % tmin)
        elif tmax:
            facts.append("It needs a surface cooler than %d kelvin." % tmax)
        if rule.get("stars"):
            facts.append("It only turns up in systems with certain kinds of star.")
        if rule.get("v") or rule.get("vreq"):
            facts.append("It lives where there is volcanic activity.")
        if values:
            known = sorted(set(v for v in values.values() if v), reverse=True)
            mine = values.get(str(species or "").lower())
            if mine and len(known) >= 10:
                rank = known.index(mine) + 1
                facts.append("Out of the species I have prices for, it ranks number %d by value." % rank if rank <= 10
                             else "Among the species I have prices for, it sits in the %s half by value." % ("top" if rank <= len(known) / 2 else "bottom"))
        metres = (distances or {}).get(str(genus or rule.get("g") or "").lower())
        if metres:
            facts.append("Samples of this kind need to be at least %d metres apart." % metres)
        return facts

    def pool(self, species, genus="", values=None, distances=None):
        name = ("%s %s" % (species or "", genus or "")).lower()
        key = str(species or "").lower()
        out = []
        match = next((g for g in sorted(self.genus, key=len, reverse=True) if g in name), None)
        if match:
            out += self.genus[match]
        if key in self.species:
            out.append(self.species[key])
        out += self.habitat_facts(species, values, distances, genus)
        return out

    def about(self, species, genus="", count=1, values=None, distances=None):
        """`count` different facts about the species as one piece of text ('' if there is nothing to say)."""
        key = str(species or "").lower()
        pool = self.pool(species, genus, values, distances)
        if not pool:
            return ""
        chosen = []
        for _ in range(max(1, count)):
            left = [t for t in self._left.get(key, []) if t in pool]
            if not left:                                       # a new round: everything again, but not the one just told first
                left = [t for t in pool if t != self._last.get(key)] or list(pool)
                self.rng.shuffle(left)
            fact = left.pop(0)
            self._left[key] = left
            self._last[key] = fact
            if fact not in chosen:
                chosen.append(fact)
        return " ".join(chosen)


THIRD_FACT_CHANCE = 0.6          # how often the third sample comes with one more fact


class ExobiologyTracker:
    def __init__(self, values_file=None, data_dir=None, info_file=None, rng=None):
        seed = _read_json(values_file) if values_file else {}
        self.multiplier = seed.get("first_footfall_multiplier", DEFAULT_MULTIPLIER)
        self.distances = {str(k).lower(): int(v) for k, v in (seed.get("colony_distance_m") or {}).items()
                          if isinstance(v, (int, float))}
        self.seed = {str(k).lower(): int(v) for k, v in (seed.get("values") or {}).items()
                     if isinstance(v, (int, float))}
        self._learned_file = Path(data_dir) / "exobiology_learned.json" if data_dir else None
        self._carried_file = Path(data_dir) / "exobiology_carried.json" if data_dir else None
        learned = _read_json(self._learned_file) if self._learned_file else {}
        self.learned = {str(k).lower(): int(v) for k, v in learned.items() if isinstance(v, (int, float))}
        carried = _read_json(self._carried_file) if self._carried_file else {}
        self.carried = [c for c in carried.get("items", []) if isinstance(c, dict)]
        self.last_timestamp = str(carried.get("last_timestamp") or "")
        if info_file is None and values_file:
            info_file = Path(values_file).with_name("bio_info.json")
        rules_file = Path(values_file).with_name("bio_rules.json") if values_file else None
        self.info = BioInfo(info_file, rng, rules_file)
        self.progress = None       # the species you are sampling right now
        self.footfall = {}         # (SystemAddress, BodyID) -> WasFootfalled, first value seen

    # ---- prices ----
    def base_value(self, species):
        key = str(species or "").lower()
        return self.learned.get(key) or self.seed.get(key)

    def top_threshold(self):
        """The value of the 10th most valuable species we know. None when we know fewer than 10 species."""
        merged = {**self.seed, **self.learned}
        values = sorted(merged.values(), reverse=True)
        return values[TOP_N - 1] if len(values) >= TOP_N else None

    def is_top(self, species):
        """True for the ten most valuable species (ties with the 10th count too)."""
        base, threshold = self.base_value(species), self.top_threshold()
        return base is not None and threshold is not None and base >= threshold

    def price_is_exact(self, species):
        return str(species or "").lower() in self.learned

    def colony_distance(self, entry):
        """How many metres the next sample must be from this one (by genus), or None if unknown."""
        text = ("%s %s" % (entry.get("Genus_Localised") or "", entry.get("Species_Localised") or "")).lower()
        for genus, metres in self.distances.items():
            if genus in text:
                return metres
        return None

    # ---- bodies (from Scan events) ----
    def note_body(self, entry):
        if "WasFootfalled" not in entry:
            return
        key = (entry.get("SystemAddress"), entry.get("BodyID"))
        if key[1] is None or key in self.footfall:
            return      # keep the FIRST value we saw: it is the one from before you landed
        if len(self.footfall) >= MAX_REMEMBERED_BODIES:
            self.footfall.pop(next(iter(self.footfall)))
        self.footfall[key] = bool(entry.get("WasFootfalled"))

    def first_footfall(self, entry):
        key = (entry.get("SystemAddress"), entry.get("Body"))
        return self.footfall.get(key) is False

    # ---- taking samples ----
    def on_scan_organic(self, entry):
        """Returns extra information to attach to the ScanOrganic event."""
        stage = entry.get("ScanType")
        species = entry.get("Species_Localised") or entry.get("Genus_Localised") or ""
        body = (entry.get("SystemAddress"), entry.get("Body"))

        if stage == "Log":
            self.progress = {"species": species, "body": body, "count": 1}
        elif stage == "Sample":
            p = self.progress
            if p and p["species"] == species and p["body"] == body:
                p["count"] = min(3, p["count"] + 1)
            else:
                self.progress = {"species": species, "body": body, "count": 2}
        elif stage == "Analyse":
            self.progress = {"species": species, "body": body, "count": 3}
        number = self.progress["count"] if self.progress else 1
        info = {"SampleNumber": number, "Complete": stage == "Analyse"}
        if stage == "Log":
            metres = self.colony_distance(entry)
            if metres:
                info["distance"] = str(metres)
            info.update(self._valued(entry, species))        # she tells you what it is worth on the FIRST sample
        elif stage == "Sample" and number == 2:
            about = self.info.about(species, entry.get("Genus_Localised") or "", 2, self._prices(), self.distances)
            if about:
                info["About"] = about                        # and what it is, on the second
        elif stage == "Sample" and number == 3 and self.rng_chance() < THIRD_FACT_CHANCE:
            about = self.info.about(species, entry.get("Genus_Localised") or "", 1, self._prices(), self.distances)
            if about:
                info["About"] = about                        # and sometimes one more thing on the third

        if stage == "Analyse":
            info.update(self._complete(entry, species))
            self.progress = None
        return info

    def _prices(self):
        prices = dict(self.seed)
        prices.update(self.learned)
        return prices

    def rng_chance(self):
        return self.info.rng.random()

    def _valued(self, entry, species):
        base = self.base_value(species)
        if base is None:
            return {"ValueKnown": False}
        footfall = self.first_footfall(entry)
        worth = base * (self.multiplier if footfall else 1)
        return {"ValueKnown": True, "worth": spoken_credits(worth), "FirstFootfall": bool(footfall),
                "Top10": self.is_top(species), "ExactPrice": self.price_is_exact(species)}

    def _complete(self, entry, species):
        base = self.base_value(species)
        stamp = str(entry.get("timestamp") or "")
        is_new = not (stamp and stamp <= self.last_timestamp)   # history replay: do not count twice
        footfall = self.first_footfall(entry)
        info = {"ValueKnown": base is not None, "FirstFootfall": bool(footfall and base is not None),
                "ExactPrice": self.price_is_exact(species)}
        if base is None:
            return info
        worth = base * (self.multiplier if footfall else 1)
        if is_new:
            self.carried.append({"species": species, "worth": int(worth), "footfall": bool(footfall)})
            if stamp:
                self.last_timestamp = stamp
            self._save_carried()
        info["worth"] = spoken_credits(worth)
        info["carried"] = spoken_credits(self.carried_total())
        return info

    def carried_total(self):
        return sum(int(c.get("worth", 0)) for c in self.carried)

    # ---- selling and dying ----
    def on_sell(self, entry):
        stamp = str(entry.get("timestamp") or "")
        if stamp and stamp <= self.last_timestamp:
            return                          # old history being replayed
        for item in entry.get("BioData") or []:
            if not isinstance(item, dict):
                continue
            species = item.get("Species_Localised")
            value = item.get("Value")
            if species and isinstance(value, (int, float)) and value > 0:
                self.learned[str(species).lower()] = int(value)
        _write_json(self._learned_file, self.learned) if self._learned_file else None
        self.carried = []
        if stamp:
            self.last_timestamp = stamp
        self._save_carried()

    def on_death(self, entry):
        stamp = str(entry.get("timestamp") or "")
        if stamp and stamp <= self.last_timestamp:
            return
        self.carried = []
        self.progress = None
        if stamp:
            self.last_timestamp = stamp
        self._save_carried()

    def _save_carried(self):
        if self._carried_file:
            _write_json(self._carried_file, {"items": self.carried, "last_timestamp": self.last_timestamp})
