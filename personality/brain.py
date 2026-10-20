"""
THE BRAIN - she answers things you were never "supposed" to ask, without any AI model.

How it works (all of it is plain text files, tiny and instant):
  * config/brain_intents.json says which sentences mean what ("what's your favourite colour" -> Brain_FavColour).
  * voicepacks/default/brain.json holds her answers, one pool per topic, with mood variants (_Friendly, _Close,
    _Sarcastic, _Frustrated) like every other line she has. A topic can also have _More and _Why pools.
  * Some answers use the REAL game: where you are, your ship, hull and shields, how long you have been playing, the time.
  * She remembers the last topic for a couple of minutes, so "why?", "tell me more", "really?" and "what about you?" work.
  * Riddles: she asks one, waits for your guess, and tells you the answer if you give up (voicepacks/default/riddles.json).

She only uses this when you are talking to HER (wake word or push-to-talk) AND the sentence is not a game command, so it can
never steal a command. If nothing here fits, the normal "I didn't catch that" happens.
"""
import json
import random
import re
import time
from datetime import datetime

from core import paths
from core.identity import personalise
from core.logger import get_logger
from core.ships import ship_name
from mining import minerals
from personality.mood_engine import effective_mood
from personality.smalltalk import clean

log = get_logger("brain")

TOPIC_SECONDS = 150.0          # how long "why?" and "tell me more" still refer to the last answer
RIDDLE_SECONDS = 120.0
FOLLOW_UPS = ("why", "more", "you", "really")
HARDPOINTS_BIT = 6


def load_intents(path=None):
    """[(intent dict, [compiled patterns])]. A broken pattern is skipped (and logged), never fatal."""
    path = path or (paths.CONFIG_DIR / "brain_intents.json")
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        log.exception("Could not read %s", path)
        return []
    intents = []
    for item in raw.get("intents", []):
        compiled = []
        for pattern in item.get("patterns", []):
            try:
                compiled.append(re.compile(pattern))
            except re.error:
                log.warning("Bad brain pattern for %s: %s", item.get("key"), pattern)
        if item.get("key") and compiled:
            intents.append((item, compiled))
    return intents


def strip_address(tidy):
    """Take 'hey starling,' off the front."""
    return re.sub(r"^(?:hey |hi |ok |okay |oi )?(?:starling )", "", tidy) or tidy


class Brain:
    def __init__(self, speech, dialogue, settings, state_provider=None, chitchat=None, facts=None, intents=None,
                 clock=time.monotonic, rng=None, now=datetime.now, mining=None, prices=None):
        self.speech = speech
        self.dialogue = dialogue
        self.settings = settings
        self.state_provider = state_provider or (lambda: None)
        self.chitchat = chitchat
        self.mining = mining         # mining/tracker.py: what you have refined this session
        self.prices = prices         # mining/prices.py: where to sell it
        self.facts = facts
        self.intents = intents if intents is not None else load_intents()
        self.clock = clock
        self.rng = rng or random.Random()
        self.now = now
        self.topic = None            # (key, time) of the last thing she talked about
        self.riddle = None           # (answers, text, time)
        self._riddles = None
        self._riddle_order = []

    # ---- what the runner asks ----
    def waiting(self):
        """True while she is waiting for a riddle answer (so a guess works without her name)."""
        return self.riddle is not None and self.clock() - self.riddle[2] < RIDDLE_SECONDS

    def try_handle(self, text, deliberate=True):
        """Answer. Returns what she said, or None when this wasn't something she can answer."""
        if self.dialogue is None or not self.settings.get("brain.enabled", True):
            return None
        tidy = strip_address(clean(text))
        if not tidy:
            return None
        if self.waiting():
            reply = self._riddle_guess(tidy)
            if reply is not None:
                return reply
        if not deliberate:
            return None
        for item, patterns in self.intents:
            for pattern in patterns:
                found = pattern.search(tidy)
                if found:
                    reply = self._answer(item, found, tidy)
                    if reply is not None:
                        return reply
                    break                      # that topic had nothing to say: try the next topic
        return None

    # ---- answering ----
    def mood(self):
        if self.settings.get("personality.style", "personality") != "personality":
            return ""
        return effective_mood(self.settings) or ""

    def _allow(self):
        return bool(self.settings.get("speech.allow_mature", False))

    def _answer(self, item, found, tidy):
        key, kind = item["key"], item.get("kind", "line")
        if kind in FOLLOW_UPS:
            return self._follow_up(kind)
        handler = getattr(self, "_do_" + kind, None)
        if handler is None:
            return self._say_pool(key, {}, remember=True)
        return handler(item, found, tidy)

    def _format(self, key, values, mood=None):
        """A line from the pool that she has every value for (None if there isn't one)."""
        mood = self.mood() if mood is None else mood
        for _ in range(10):
            line = self.dialogue.pick(key, mood, self._allow(), False)
            if line is None:
                return None
            try:
                return line.text.format(**values)
            except (KeyError, IndexError, ValueError):
                continue
        return None

    def _say(self, text):
        text = personalise(text.replace("{name}", "Starling"), self.settings)
        if self.speech is not None and self.settings.get("speech.enabled", True):
            self.speech.say(text=text, priority="normal", event_name="brain")
        return text.replace("||", " ")

    def _say_pool(self, key, values, remember=False):
        text = self._format(key, values)
        if text is None:
            return None
        if remember:
            self.topic = (key, self.clock())
        return self._say(text)

    def _follow_up(self, kind):
        if self.topic is None or self.clock() - self.topic[1] > TOPIC_SECONDS:
            return None
        key = self.topic[0]
        suffix = {"why": "_Why", "more": "_More", "you": "_You", "really": "_Really"}[kind]
        generic = {"why": "Brain_WhyGeneric", "more": "Brain_MoreGeneric", "you": "Brain_YouGeneric",
                   "really": "Brain_ReallyGeneric"}[kind]
        text = self._format(key + suffix, {}) or self._format(generic, {})
        if text is None:
            return None
        self.topic = (key, self.clock())
        return self._say(text)

    # ---- the real game ----
    def _state(self):
        return self.state_provider()

    def _values(self):
        """Real things she can mention. Missing ones are left out, so a line needing them is never used."""
        state = self._state()
        values = {}
        ship = getattr(state, "ship", None)
        if ship:
            values["ship"] = ship_name(ship)
        if getattr(state, "ship_name", None):
            values["shipname"] = state.ship_name
        if getattr(state, "system", None):
            values["system"] = state.system
        if getattr(state, "docked", False) and getattr(state, "station", None):
            values["station"] = state.station
        if getattr(state, "commander", None):
            values["commander"] = state.commander
        if self.chitchat is not None:
            try:
                values.update({k: v for k, v in self.chitchat.context().items() if k in ("jumps", "distance", "minutes")})
            except Exception:
                log.exception("Could not read the trip details")
        return values

    def _do_game(self, item, found, tidy):
        """Any answer built from the game: tries <Key>_Docked first when she is docked."""
        key = item["key"]
        values = self._values()
        if item.get("needs") and any(need not in values for need in item["needs"]):
            return self._say_pool(key + "_Unknown", {}, remember=False)
        if "station" in values and self._format_exists(key + "_Docked"):
            text = self._format(key + "_Docked", values)
            if text:
                self.topic = (key, self.clock())
                return self._say(text)
        text = self._format(key, values)
        if text is None:
            return self._say_pool(key + "_Unknown", {}, remember=False)
        self.topic = (key, self.clock())
        return self._say(text)

    def _format_exists(self, key):
        return bool(self.dialogue.pool(key, "", self._allow(), False))

    # ---- mining ----
    def _do_mined(self, item, found, tidy):
        tracker = self.mining
        if tracker is None or tracker.total() == 0:
            return self._say_pool("Brain_Mined_None", {}, remember=True)
        values = {"total": tracker.total(), "best_text": tracker.best_text()}
        return self._say_pool("Brain_Mined", values, remember=True)

    def _do_sellprice(self, item, found, tidy):
        """'Where should I sell the platinum?' Looks up the best nearby buyers in the background and says the answer."""
        if self.prices is None or not self.prices.enabled():
            return self._say_pool("Price_Disabled", {}, remember=False)
        commodity = minerals.from_speech(tidy) or (self.mining.to_sell() if self.mining is not None else None)
        if not commodity:
            return self._say_pool("Price_Which", {}, remember=False)
        system = getattr(self._state(), "system", None)
        if not system:
            return self._say_pool("Price_NoSystem", {}, remember=False)
        material = minerals.spoken(commodity)
        first = self._say_pool("Price_Looking", {}, remember=False)

        def done(results, ok):
            self._say_prices(material, results, ok)
        self.prices.lookup_async(system, commodity, done)
        return first

    @staticmethod
    def _commodity_from(tidy):
        """'where can i buy some liquid oxygen' -> ('liquidoxygen', 'Liquid Oxygen'). Minerals use their known names."""
        known = minerals.from_speech(tidy)
        if known:
            return known, minerals.spoken(known)
        found = re.search(r"\b(?:buy|get|find|purchase|sells?|selling|cheapest|pick up|priced?)\s+(?:some |any |the |a |an |more |lowest |best )*([a-z ]{3,30}?)(?: near| around| close| here| nearby| in | for | at | from | please|$)", tidy)
        if not found:
            return None, ""
        words = [w for w in found.group(1).split() if w not in ("some", "any", "the", "a", "an", "my", "our", "price", "prices", "priced")]
        if not words:
            return None, ""
        return "".join(words), " ".join(w.capitalize() for w in words)

    def _do_buyprice(self, item, found, tidy):
        """'Where can I buy tritium?' Looks up the cheapest nearby sellers in the background and says the answer."""
        if self.prices is None or not self.prices.enabled():
            return self._say_pool("Price_Disabled", {}, remember=False)
        commodity, material = self._commodity_from(tidy)
        if not commodity:
            return self._say_pool("Buy_Which", {}, remember=False)
        system = getattr(self._state(), "system", None)
        if not system:
            return self._say_pool("Price_NoSystem", {}, remember=False)
        first = self._say_pool("Buy_Looking", {}, remember=False)
        self.prices.lookup_async(system, commodity, lambda results, ok: self._say_buy(material, results, ok), mode="buy")
        return first

    def _say_buy(self, material, results, ok):
        if not ok:
            return self._say_pool("Price_Offline", {})
        if not results:
            return self._say_pool("Buy_None", {"Material": material})
        best = results[0]
        values = {"Material": material, "Price": "{:,}".format(best["price"]), "Station": best["station"],
                  "Where": self._where(best), "Stock": "{:,}".format(best.get("stock") or 0)}
        text = self._format("Buy_Found", values)
        if text is None:
            return None
        if best.get("pad"):
            text += "||%s landing pads." % best["pad"].capitalize()
        if len(results) > 1:
            second = results[1]
            more = self._format("Buy_Second", {"Price2": "{:,}".format(second["price"]), "Station2": second["station"],
                                               "Where2": self._where(second)})
            if more:
                text += "||" + more
        return self._say(text)

    @staticmethod
    def _where(result):
        distance = result.get("distance")
        if isinstance(distance, (int, float)) and distance >= 0.5:
            return "in %s, %s light years away" % (result["system"], int(round(distance)))
        return "in %s" % result["system"]

    def _say_prices(self, material, results, ok):
        if not ok:
            return self._say_pool("Price_Offline", {})
        if not results:
            return self._say_pool("Price_None", {"Material": material})
        best = results[0]
        values = {"Material": material, "Price": "{:,}".format(best["price"]), "Station": best["station"],
                  "Where": self._where(best)}
        text = self._format("Price_Found", values)
        if text is None:
            return None
        if best.get("pad"):
            text += "||%s landing pads." % best["pad"].capitalize()
        if len(results) > 1:
            second = results[1]
            more = self._format("Price_Second", {"Price2": "{:,}".format(second["price"]), "Station2": second["station"],
                                                  "Where2": self._where(second)})
            if more:
                text += "||" + more
        return self._say(text)

    def _do_status(self, item, found, tidy):
        state = self._state()
        if state is None:
            return self._say_pool("Brain_Status_Unknown", {})
        hull = int(round(float(getattr(state, "hull_health", 1.0) or 0) * 100))
        values = {"hull": hull, "shields": "up" if getattr(state, "shields_up", True) else "down"}
        key = "Brain_Status_Low" if hull < 50 else ("Brain_Status_Down" if values["shields"] == "down" else "Brain_Status")
        text = self._format(key, values) or self._format("Brain_Status", values)
        if text is None:
            return None
        if getattr(state, "wanted", False):
            extra = self._format("Brain_Status_Wanted", {})
            if extra:
                text += "||" + extra
        self.topic = ("Brain_Status", self.clock())
        return self._say(text)

    def _do_wanted(self, item, found, tidy):
        state = self._state()
        key = "Brain_Wanted_Yes" if getattr(state, "wanted", False) else "Brain_Wanted_No"
        return self._say_pool(key, {}, remember=True)

    def _do_time(self, item, found, tidy):
        moment = self.now()
        hour = moment.hour
        period = "morning" if 5 <= hour < 12 else "afternoon" if 12 <= hour < 17 else "evening" if 17 <= hour < 22 else "night"
        values = {"time": moment.strftime("%H:%M"), "period": period}
        return self._say_pool("Brain_Time", values, remember=True)

    def _do_date(self, item, found, tidy):
        moment = self.now()
        day = moment.day
        suffix = "th" if 10 <= day % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        values = {"date": "%s the %d%s of %s" % (moment.strftime("%A"), day, suffix, moment.strftime("%B"))}
        return self._say_pool("Brain_Date", values, remember=True)

    def _do_suggest(self, item, found, tidy):
        state = self._state()
        flags = getattr(state, "status_flags", 0) or 0
        if float(getattr(state, "hull_health", 1.0) or 1.0) < 0.5:
            key = "Brain_Suggest_Repair"
        elif getattr(state, "wanted", False):
            key = "Brain_Suggest_Wanted"
        elif (flags >> HARDPOINTS_BIT) & 1:
            key = "Brain_Suggest_Combat"
        elif getattr(state, "docked", False):
            key = "Brain_Suggest_Docked"
        elif getattr(state, "in_supercruise", False):
            key = "Brain_Suggest_Supercruise"
        else:
            key = "Brain_Suggest_Flying"
        text = self._format(key, self._values()) or self._format("Brain_Suggest", self._values())
        if text is None:
            return None
        self.topic = ("Brain_Suggest", self.clock())
        return self._say(text)

    # ---- dice and decisions ----
    def _do_coin(self, item, found, tidy):
        return self._say_pool("Brain_Coin", {"result": self.rng.choice(["Heads", "Tails"])}, remember=True)

    def _do_dice(self, item, found, tidy):
        sides = 6
        match = re.search(r"\bd(\d{1,3})\b|(\d{1,3}) sided", tidy)
        if match:
            sides = int(match.group(1) or match.group(2))
        sides = min(max(sides, 2), 100)
        return self._say_pool("Brain_Dice", {"result": self.rng.randint(1, sides), "sides": sides}, remember=True)

    def _do_number(self, item, found, tidy):
        low, high = 1, 10
        match = re.search(r"between (\d{1,6}) and (\d{1,6})", tidy)
        if match:
            low, high = sorted((int(match.group(1)), int(match.group(2))))
        return self._say_pool("Brain_Number", {"result": self.rng.randint(low, high), "low": low, "high": high}, remember=True)

    def _do_opinion(self, item, found, tidy):
        thing = (found.groupdict().get("t") or "").strip()
        thing = re.sub(r"^(?:the|a|an|my|your|this|that) ", "", thing)
        if not thing or len(thing) > 40 or len(thing.split()) > 5:
            return None
        return self._say_pool("Brain_Opinion", {"topic": thing}, remember=True)

    def _do_fact(self, item, found, tidy):
        if self.facts is None:
            return None
        fact = self.facts.next(str(self.settings.get("facts.topics", "all")))
        if not fact:
            return None
        intro = self._format("Brain_FactIntro", {}) or ""
        self.topic = ("Brain_Fact", self.clock())
        return self._say((intro + "||" if intro else "") + fact)

    def _do_name(self, item, found, tidy):
        return self._do_game(item, found, tidy)

    # ---- riddles ----
    def _load_riddles(self):
        if self._riddles is None:
            self._riddles = []
            folder = getattr(self.dialogue, "pack_dir", None)
            if folder is not None:
                try:
                    with open(folder / "riddles.json", encoding="utf-8") as handle:
                        self._riddles = [r for r in json.load(handle).get("riddles", []) if r.get("q") and r.get("answers")]
                except (OSError, ValueError):
                    log.warning("No riddles file found")
        return self._riddles

    def _do_riddle(self, item, found, tidy):
        riddles = self._load_riddles()
        if not riddles:
            return None
        if not self._riddle_order:
            self._riddle_order = list(range(len(riddles)))
            self.rng.shuffle(self._riddle_order)
        riddle = riddles[self._riddle_order.pop()]
        answers = [clean(a) for a in riddle["answers"]]
        intro = self._format("Brain_RiddleIntro", {}) or ""
        self.riddle = (answers, riddle.get("a") or riddle["answers"][0], self.clock())
        self.topic = ("Brain_Riddle", self.clock())
        return self._say((intro + "||" if intro else "") + riddle["q"])

    def _do_riddle_answer(self, item, found, tidy):
        """'I give up' / 'what's the answer'."""
        if self.riddle is None:
            return None
        text = self.riddle[1]
        self.riddle = None
        return self._say_pool("Brain_RiddleReveal", {"answer": text})

    def _riddle_guess(self, tidy):
        answers = self.riddle[0]
        words = " %s " % tidy
        if any((" %s " % answer) in words for answer in answers):
            self.riddle = None
            return self._say_pool("Brain_RiddleRight", {})
        return None
