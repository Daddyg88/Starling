"""LIVE ANSWERS: questions about your own ship and about biology payouts, understood however you word them.

She already knew the ANSWERS (the fuel gauge, the hull, the cargo hold, the price of every species). What she did not know was the
QUESTIONS: the brain's patterns are exact sentences, so "how much fuel do I have left" worked for nobody. Here a question is understood by
its important words instead: a topic word (fuel, hull, cargo, jump range, exobiology...) plus a word that shows you are asking about a
quantity or about yourself (how much, left, my, level, highest, worth...). "What's my fuel level?", "have I got enough fuel?" and "how much
fuel is left in the tank" are all the same question.

It only ever READS her notes of the game (state) and the price list; it never presses a key. When she does not know the number yet
(the game has not told her), she says so instead of guessing. Her words are in voicepacks/default/live.json (Live_* keys).
"""

import re

from personality.ships_info import say_credits, say_number

MIN_WORDS = 2


def words_of(text):
    return re.findall(r"[a-z0-9]+", str(text or "").lower().replace("'", "").replace("’", ""))


def _any(words, group):
    return bool(words & group)


FUEL = {"fuel", "tank", "gas", "petrol", "fuels"}
FUEL_NOT = {"scoop", "scooping", "scoops", "rat", "rats", "tritium", "price", "cost", "buy", "sell", "synthesis", "carrier", "cell", "cells",
            "limpet", "limpets", "capacity"}
ASKING = {"much", "many", "left", "remaining", "remain", "level", "levels", "percent", "percentage", "enough", "low", "got", "have", "my", "our",
          "how", "check", "whats", "what", "status", "gauge", "state", "condition", "at", "am", "are", "do", "does", "is"}
SELF = {"my", "i", "we", "our", "me", "have", "got", "left", "remaining", "level", "enough", "low", "percent", "much", "status", "condition"}
HULL = {"hull", "armour", "armor", "integrity", "damaged", "damage", "hp"}
SHIELDS = {"shield", "shields"}
CARGO = {"cargo", "hold"}
CARGO_ASK = {"much", "many", "space", "room", "capacity", "full", "carrying", "carry", "left", "free", "have", "got", "my", "empty", "load"}
BIO = {"exobiology", "exobiologist", "exobio", "biology", "bio", "bios", "biological", "organic", "organics", "species", "flora", "lifeform",
       "lifeforms", "samples", "sample", "biologicals"}
BEST = {"highest", "most", "best", "top", "biggest", "maximum", "max", "richest", "greatest", "priciest", "expensive", "valuable",
        "lucrative", "largest", "better", "pays", "paying"}
WORST = {"lowest", "cheapest", "least", "worst", "smallest", "minimum", "poorest", "lowestpaying"}
MONEY = {"payout", "payouts", "pay", "pays", "paying", "worth", "value", "values", "valuable", "credits", "price", "prices", "payment",
         "reward", "earn", "earns", "money", "sell", "sale", "profit", "much", "get", "paid"}


class LiveAnswers:
    """answer(text, state) -> (dialogue key, values) or None."""

    def __init__(self, state_provider=None):
        self.state_provider = state_provider

    def _state(self):
        return self.state_provider() if self.state_provider else None

    def answer(self, text, state=None):
        said = words_of(text)
        if len(said) < MIN_WORDS:
            return None
        state = state if state is not None else self._state()
        if state is None:
            return None
        words = set(said)
        joined = " ".join(said)
        for check in (self._bio, self._fuel, self._hull, self._shields, self._cargo, self._range, self._jumps, self._material):
            found = check(words, joined, state)
            if found is not None:
                return found
        return None

    # ---- the ship ----
    @staticmethod
    def _fuel(words, joined, state):
        if not _any(words, FUEL) or _any(words, FUEL_NOT) or not _any(words, SELF):
            return None
        tons = getattr(state, "fuel_main", None)
        if tons is None:
            return "Live_Fuel_Unknown", {}
        capacity = getattr(state, "fuel_capacity", None)
        values = {"tons": say_number(tons)}
        if capacity:
            percent = int(round(100.0 * tons / float(capacity)))
            values.update(percent=percent, capacity=say_number(capacity))
            return ("Live_Fuel_Low" if percent <= 25 else "Live_Fuel"), values
        return "Live_Fuel_Tons", values

    @staticmethod
    def _hull(words, joined, state):
        if not _any(words, HULL) or not _any(words, ASKING | SELF):
            return None
        hull = int(round(float(getattr(state, "hull_health", 1.0) or 0) * 100))
        return ("Live_Hull_Low" if hull < 50 else "Live_Hull"), {"hull": hull}

    @staticmethod
    def _shields(words, joined, state):
        if not _any(words, SHIELDS) or not _any(words, ASKING | SELF):
            return None
        return ("Live_Shields_Up" if getattr(state, "shields_up", True) else "Live_Shields_Down"), {}

    @staticmethod
    def _cargo(words, joined, state):
        if not _any(words, CARGO) or not _any(words, CARGO_ASK) or _any(words, {"sell", "buy", "price", "best", "worth"}):
            return None
        capacity = getattr(state, "cargo_capacity", None)
        carried = getattr(state, "cargo_tons", None)
        if capacity is None and carried is None:
            return "Live_Cargo_Unknown", {}
        if capacity is None:
            return "Live_Cargo_Carried", {"carried": say_number(carried)}
        carried = float(carried or 0)
        if carried <= 0:
            return "Live_Cargo_Empty", {"capacity": say_number(capacity)}
        return "Live_Cargo", {"carried": say_number(carried), "capacity": say_number(capacity), "free": say_number(max(0.0, capacity - carried))}

    @staticmethod
    def _range(words, joined, state):
        if not (("range" in words and ("jump" in words or "fsd" in words or "my" in words)) or ("far" in words and "jump" in words and "can" in words)):
            return None
        value = getattr(state, "max_jump_range", None)
        if not value:
            return "Live_Range_Unknown", {}
        return "Live_Range", {"range": say_number(value)}

    @staticmethod
    def _jumps(words, joined, state):
        if "jumps" not in words and "jump" not in words:
            return None
        if not _any(words, {"left", "remaining", "togo", "more"}) and "to go" not in joined:
            return None
        if _any(words, {"made", "done", "total", "made", "ive"}):
            return None
        if "range" in words:
            return None
        left = getattr(state, "route_jumps_left", None)
        if left is None:
            return "Live_Jumps_None", {}
        return "Live_Jumps", {"jumps": left, "s": "" if left == 1 else "s"}

    @staticmethod
    def _material(words, joined, state):
        held = getattr(state, "materials", None) or {}
        if not held or not _any(words, {"much", "many", "have", "got", "holding", "carrying", "left", "do"}):
            return None
        for name in sorted(held, key=len, reverse=True):
            if re.search(r"\b%s\b" % re.escape(str(name).lower()), joined):
                return "Live_Material", {"name": str(name), "count": held[name]}
        return None

    # ---- exobiology payouts ----
    def _bio(self, words, joined, state):
        tracker = getattr(state, "exobiology", None)
        prices = tracker._prices() if tracker is not None and hasattr(tracker, "_prices") else {}
        if not prices:
            return None
        species = self._species_in(joined, prices)
        if species is not None:
            return "Live_Bio_Species", {"name": species.title(), "value": say_credits(prices[species])}
        genus = self._genus_in(joined, tracker, prices)
        if genus is not None and _any(words, MONEY | BEST | WORST):
            members = sorted(((n, v) for n, v in prices.items() if n.startswith(genus + " ")), key=lambda kv: -kv[1])
            if members:
                return "Live_Bio_Genus", {"genus": genus.title(), "best": members[0][0].title(), "best_value": say_credits(members[0][1]),
                                          "worst_value": say_credits(members[-1][1])}
        if not _any(words, BIO) or not _any(words, BEST | WORST):
            return None
        ranked = sorted(prices.items(), key=lambda kv: -kv[1])
        if _any(words, WORST) and not _any(words, BEST - {"most", "pays", "paying"}):
            ranked = list(reversed(ranked))
            key = "Live_Bio_Worst"
        else:
            key = "Live_Bio_Best"
        (a, av), (b, bv) = ranked[0], ranked[1]
        return key, {"name": a.title(), "value": say_credits(av), "second": b.title(), "second_value": say_credits(bv)}

    @staticmethod
    def _species_in(joined, prices):
        for name in sorted(prices, key=len, reverse=True):
            if len(name.split()) >= 2 and re.search(r"\b%s\b" % re.escape(name), joined):
                return name
        return None

    @staticmethod
    def _genus_in(joined, tracker, prices):
        genera = set(getattr(tracker, "distances", {}) or {})
        for genus in sorted(genera, key=len, reverse=True):
            if re.search(r"\b%s\b" % re.escape(genus), joined) and any(n.startswith(genus + " ") for n in prices):
                return genus
        return None
