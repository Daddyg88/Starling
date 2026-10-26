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


class BioInfo:
    """Short, checked descriptions of what she has just sampled (config/bio_info.json). Says nothing if she has none."""

    def __init__(self, path=None, rng=None):
        data = _read_json(path) if path else {}
        self.genus = {str(k).lower(): [str(t) for t in v if t] for k, v in (data.get("genus") or {}).items()
                      if isinstance(v, list)}
        self.species = {str(k).lower(): str(v) for k, v in (data.get("species") or {}).items() if v}
        self.rng = rng or random.Random()
        self._last = {}

    def about(self, species, genus=""):
        """The description for a species as one piece of text ('' if there is nothing to say)."""
        name = ("%s %s" % (species or "", genus or "")).lower()
        key = str(species or "").lower()
        parts = []
        match = next((g for g in sorted(self.genus, key=len, reverse=True) if g in name), None)
        if match and self.genus[match]:
            options = self.genus[match]
            fresh = [t for t in options if t != self._last.get(match)] or options
            choice = self.rng.choice(fresh)
            self._last[match] = choice
            parts.append(choice)
        if key in self.species:
            parts.append(self.species[key])
        return " ".join(parts)


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
        self.info = BioInfo(info_file, rng)
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
            about = self.info.about(species, entry.get("Genus_Localised") or "")
            if about:
                info["About"] = about                        # and what it is, on the second

        if stage == "Analyse":
            info.update(self._complete(entry, species))
            self.progress = None
        return info

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
