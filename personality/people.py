"""
PEOPLE SHE HAS HEARD ABOUT - "my friend Andrew from Germany".

She keeps a tiny address book in data/people.json (on your PC only, never uploaded, and it is in .gitignore).
  Learns:   "my friend Andrew is from Germany", "my brother is called Tom", "Sarah is my wife"
  Recalls:  "who is Andrew?", "where is Andrew from?", "who do you know?"
  Forgets:  "forget Andrew", "forget everyone"
Her wording lives in config/knowledge/style.json (the people_* lists).
"""

import json
import os
import re
import tempfile
import threading

from core.logger import get_logger

log = get_logger("people")

MAX_PEOPLE = 40
RELATIONS = ("friend", "mate", "brother", "sister", "mum", "mom", "mother", "dad", "father", "wife", "husband", "partner",
             "girlfriend", "boyfriend", "son", "daughter", "cousin", "uncle", "aunt", "auntie", "nephew", "niece", "grandma",
             "grandad", "grandpa", "grandmother", "grandfather", "colleague", "boss", "neighbour", "neighbor", "teacher",
             "flatmate", "roommate", "fiance", "fiancee")
NOT_NAMES = {"a", "an", "the", "is", "was", "from", "in", "called", "named", "who", "that", "this", "my", "your", "and", "so",
             "very", "really", "also", "just", "too", "not", "has", "had", "lives", "live", "he", "she", "they", "it", "back",
             "here", "there", "coming", "playing", "on", "at", "of", "to", "for", "with", "about", "like", "likes", "loves",
             "going", "gone", "ill", "sick", "better", "good", "bad", "great", "nice", "mad", "great", "starling", "you", "me", "i"}
_REL = "(?P<rel>%s)" % "|".join(RELATIONS)
_NAME = r"(?P<name>[a-z]{2,15})"
_PLACE = r"(?:\s+(?:is |who is |who lives |lives |living |that lives |that is |and (?:he|she) (?:is|lives) )?(?:from|in|lives in|living in|born in)\s+(?P<place>[a-z]{2,20}(?: [a-z]{2,20}){0,2}))?"
LEARN = [
    re.compile(r"^(?:oh |by the way |you know )?my (?:%s)? ?%s (?:is )?(?:called |named )?%s%s$" % ("", _REL, _NAME, _PLACE)),
    re.compile(r"^(?:oh |by the way )?my (?:%s)? ?%s(?: is| was)? (?:called|named) %s%s$" % ("", _REL, _NAME, _PLACE)),
    re.compile(r"^%s is my %s%s$" % (_NAME, _REL, _PLACE)),
]
WHO = re.compile(r"^(?:who is|whos|who was|do you know|do you remember|remember|tell me about|what do you know about) (?:my (?:%s) )?%s$" % ("|".join(RELATIONS), _NAME))
WHERE = re.compile(r"^where (?:is|does|was) %s (?:from|live|come from)$" % _NAME)
GREET = re.compile(r"^(?:please |can you |could you |will you )?(?:say |give )?(?:a )?(?:hello|hi|hey|good (?:morning|afternoon|evening|night)) to "
                   r"(?:my (?P<rel>%s)(?: (?P<name>[a-z]{2,15}))?|(?P<only>[a-z]{2,15}))$" % "|".join(RELATIONS))
NOT_GREETED = {"everyone", "everybody", "chat", "stream", "viewers", "guys", "folks", "all", "them", "him", "her", "us", "the", "my", "your",
               "starling", "yourself", "me", "you", "team", "squad", "wing", "wingmen", "crew", "friends"}
ALL = re.compile(r"^(?:who do you know|who have i told you about|who are my friends|who are the people (?:you know|i(?:ve| have) told you about)|what people do you know)$")
FORGET = re.compile(r"^(?:forget|please forget|forget about) (?:my (?:%s) )?(?P<who>everyone|everybody|all (?:of )?my (?:friends|people)|%s)$" % ("|".join(RELATIONS), r"[a-z]{2,15}"))


def _pretty(name):
    return name[:1].upper() + name[1:]


class People:
    def __init__(self, path):
        self.path = path
        self.items = {}                                   # "andrew" -> {"relation": "friend", "place": "Germany"}
        self._lock = threading.Lock()
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                self.items = {str(k): v for k, v in data.items() if isinstance(v, dict) and not str(k).startswith("_")}
        except FileNotFoundError:
            pass
        except Exception:
            log.warning("Could not read %s; starting an empty address book", path)

    # ---- learning ----
    def learn(self, tidy, raw=None):
        """Returns (name, relation, place, is_new) or None. When the original text is given, the name must start with a capital
        letter in it ("my wife is Sarah" is a name, "my wife is tired" is not)."""
        for pattern in LEARN:
            found = pattern.match(tidy)
            if not found:
                continue
            name = found.group("name")
            if name in NOT_NAMES or name in RELATIONS:
                return None
            if raw is not None and not re.search(r"\b" + name[:1].upper() + re.escape(name[1:]) + r"\b", raw):
                return None
            place = (found.groupdict().get("place") or "").strip()
            if place and place.split()[0] in NOT_NAMES - {"the"}:
                place = ""
            relation = found.group("rel")
            with self._lock:
                old = self.items.get(name)
                is_new = old is None
                if is_new and len(self.items) >= MAX_PEOPLE:
                    return None
                item = dict(old or {})
                item["relation"] = relation
                if place:
                    item["place"] = place.title()
                changed = is_new or item != old
                self.items[name] = item
                if changed:
                    self._save()
            return _pretty(name), relation, item.get("place", ""), is_new
        return None

    def greet(self, tidy, raw=None):
        """'Say hello to my wife Marie' / 'say hello to Andrew'. Returns a dict (name, relation, place, new) or None.
        A new name is remembered too (when it starts with a capital letter in what she heard)."""
        found = GREET.match(tidy)
        if not found:
            return None
        relation = found.group("rel") or ""
        name = found.group("name") or found.group("only") or ""
        if name in NOT_GREETED or name in NOT_NAMES or name in RELATIONS:
            name = ""
        if name and name not in self.items and raw is not None and not re.search(r"\b" + name[:1].upper() + re.escape(name[1:]) + r"\b", raw):
            name = ""                                      # no capital letter: probably not a name
        if not name and not relation:
            return None
        if not name:
            mine = [n for n, item in self.items.items() if item.get("relation") == relation]
            if len(mine) == 1:
                name = mine[0]                           # "say hello to my wife" when she already knows who the wife is
        new = False
        if name and relation:
            new = name not in self.items
            learned = self.learn("my %s %s" % (relation, name), raw.replace(",", " ") if raw else None) if new else None
            if learned is None and new:
                new = False
        elif name and name in self.items:
            relation = self.items[name].get("relation", "")
        elif name:
            relation = ""
        info = self.items.get(name, {}) if name else {}
        return {"name": _pretty(name) if name else "", "relation": relation or info.get("relation", ""), "place": info.get("place", ""), "new": new,
                "known": bool(name) and name in self.items and not new}

    # ---- recalling ----
    def who(self, tidy):
        """('who'|'where'|'all'|'forget'|'forgot_all', ...) for a question about the address book, else None."""
        if ALL.match(tidy):
            return ("all", [self.describe(n) for n in self.items])
        found = FORGET.match(tidy)
        if found:
            target = found.group("who")
            if target in ("everyone", "everybody") or target.startswith("all"):
                had = bool(self.items)
                self.clear()
                return ("forgot_all", had)
            if target in self.items:
                with self._lock:
                    self.items.pop(target, None)
                    self._save()
                return ("forgot", _pretty(target))
            return None
        found = WHERE.match(tidy)
        if found:
            name = found.group("name")
            if name in self.items:
                return ("where", self.describe(name))
            return None
        found = WHO.match(tidy)
        if found and found.group("name") in self.items:
            return ("who", self.describe(found.group("name")))
        return None

    def describe(self, name):
        item = self.items.get(name, {})
        return {"name": _pretty(name), "relation": item.get("relation", "friend"), "place": item.get("place", "")}

    def clear(self):
        with self._lock:
            self.items = {}
            try:
                os.remove(self.path)
            except OSError:
                pass

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle, temp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                json.dump(self.items, out, indent=1, ensure_ascii=False)
            os.replace(temp, self.path)
        except OSError:
            log.exception("Could not save the address book")
