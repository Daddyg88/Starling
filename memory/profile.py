"""
THE PLAYER PROFILE - small things you tell her about yourself, so she can talk to YOU instead of to "a player".

  "I love pizza"   "I hate mining"   "my dog is called Rex"   "my favourite colour is blue"

What she keeps: things you like, things you dislike, your pets' names and your favourites. That is all. It is kept in
data/player_profile.json on YOUR computer (plain text: open it, edit it, or delete it) and never sent anywhere.
She says out loud when she has learned something ("Noted, you like pizza"), so nothing is learned in secret.

What she deliberately does NOT keep: anything about health, money, religion, politics, sex, drugs or crime, other
people (family, bosses, friends), and anything that looks like a name, address or number. Only whole short sentences
count, so half-heard chatter is never turned into a "fact".

You can say "forget that I like pizza" or "forget what you know about me" (the Memory page button clears it too).
"""
import json
import os
import re
import tempfile
import threading

from core.logger import get_logger

log = get_logger("profile")

MAX_ITEMS = 30
MAX_PETS = 6
MAX_FAVS = 20
MAX_WORDS = 4
PETS = ("dog", "cat", "puppy", "kitten", "hamster", "rabbit", "parrot", "horse", "bird", "tortoise", "guinea pig", "goldfish", "snake",
        "lizard", "budgie", "ferret")
# anything with one of these words is never kept
BLOCKED = {"sex", "sexy", "porn", "drug", "drugs", "weed", "cocaine", "heroin", "meth", "gambling", "politics", "political", "trump",
           "religion", "god", "church", "mosque", "jesus", "allah", "racist", "nazi", "suicide", "death", "dying", "kill", "killing",
           "murder", "rape", "abuse", "cancer", "diabetes", "depression", "anxiety", "therapy", "medication", "pills", "debt", "loan",
           "salary", "password", "address", "phone", "number", "credit", "bank", "illness", "disease", "hospital", "alcohol", "drunk",
           "vodka", "beer", "wine", "whisky", "vote", "party", "gay", "straight", "trans", "muslim", "christian", "jewish", "hindu",
           "fuck", "shit", "cunt", "bitch"}
# other people: not hers to keep
PEOPLE = {"my", "your", "our", "mum", "mom", "dad", "wife", "husband", "boss", "girlfriend", "boyfriend", "partner", "sister", "brother",
          "son", "daughter", "kids", "children", "friend", "friends", "family", "ex", "neighbour", "neighbours", "teacher", "colleague",
          "colleagues", "people", "everyone", "everybody", "someone", "anyone", "nobody"}
NOT_THINGS = {"you", "it", "this", "that", "these", "those", "him", "her", "them", "how", "when", "what", "the way", "being", "me", "us",
              "myself", "yourself", "here", "there", "doing", "going", "not", "so", "very", "too", "much", "a lot", "lot", "really",
              "everything", "nothing", "anything", "something", "all", "both", "either", "neither", "one"}

_LIKE = re.compile(r"^i (?:really |absolutely |just |totally |do )?(?:like|love|enjoy|adore) (?:to |playing |watching |eating |drinking |"
                   r"listening to |reading |going to |going |doing |making )?(?P<x>[a-z0-9 ]{2,40})$")
_DISLIKE = re.compile(r"^i (?:really |absolutely |just |totally )?(?:hate|dislike|detest|loathe|cant stand|cannot stand|cant bear) "
                      r"(?:to |playing |watching |eating |drinking |listening to |reading |going to |going |doing |making )?(?P<x>[a-z0-9 ]{2,40})$")
_PET = re.compile(r"^(?:my (?P<k1>" + "|".join(PETS) + r") (?:is called|is named|called|named|s name is|is)|i have a (?P<k2>" + "|".join(PETS) +
                  r") (?:called|named)|we have a (?P<k3>" + "|".join(PETS) + r") (?:called|named)) (?P<n>[a-z]{2,15})$")
_FAV = re.compile(r"^my (?:favou?rite|fave) (?P<cat>[a-z]{3,14}(?: [a-z]{3,14})?) (?:is|are) (?P<x>[a-z0-9 ]{2,30})$")
_FORGET_ONE = re.compile(r"^(?:please )?(?:forget|erase|delete|remove) (?:that )?(?:i (?:like|love|enjoy|adore|hate|dislike) |my (?:dog|cat|puppy|kitten|hamster|rabbit|parrot|horse|bird|tortoise|guinea pig|goldfish|snake|lizard|budgie|ferret)(?: called| named)? |my favou?rite )?(?P<x>[a-z0-9 ]{2,40})$")
_FORGET_ALL = re.compile(r"^(?:please )?(?:forget|erase|delete|wipe|clear) (?:everything|all|what) (?:you (?:know|learned|learnt|remember)|i (?:told|said to) you|that i (?:told|said to) you)?\s*(?:about me)?$")


def _clean_thing(text):
    text = re.sub(r"^(?:the |a |an |some |any )", "", (text or "").strip())
    text = re.sub(r"\s+", " ", text)
    return text


def acceptable(thing):
    """True if this is a short, harmless THING she may keep."""
    words = thing.split()
    if not thing or len(words) > MAX_WORDS or len(thing) > 32:
        return False
    if any(w in BLOCKED or w in PEOPLE or w.isdigit() for w in words):
        return False
    if thing in NOT_THINGS or words[0] in NOT_THINGS or words[-1] in NOT_THINGS:
        return False
    return True


class PlayerProfile:
    def __init__(self, path, enabled=lambda: True):
        self.path = path
        self.enabled = enabled
        self._lock = threading.Lock()
        self.likes, self.dislikes, self.pets, self.favourites = [], [], [], {}
        self._load()

    # ---- file ----
    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return
        except Exception:
            log.warning("Could not read %s; starting a fresh profile.", self.path)
            return
        if not isinstance(data, dict):
            return
        self.likes = [str(x) for x in data.get("likes", []) if isinstance(x, str)][:MAX_ITEMS]
        self.dislikes = [str(x) for x in data.get("dislikes", []) if isinstance(x, str)][:MAX_ITEMS]
        self.pets = [{"kind": str(p.get("kind", "")), "name": str(p.get("name", ""))} for p in data.get("pets", [])
                     if isinstance(p, dict) and p.get("name")][:MAX_PETS]
        favs = data.get("favourites", {})
        self.favourites = {str(k): str(v) for k, v in favs.items()} if isinstance(favs, dict) else {}

    def save(self):
        try:
            os.makedirs(os.path.dirname(str(self.path)) or ".", exist_ok=True)
            handle, temp = tempfile.mkstemp(dir=os.path.dirname(str(self.path)) or ".", suffix=".tmp")
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                json.dump({"_help": "What she has learned about you. Plain text, only on this computer. Edit it or delete it any time.",
                           "likes": self.likes, "dislikes": self.dislikes, "pets": self.pets, "favourites": self.favourites},
                          out, indent=1)
            os.replace(temp, self.path)
        except Exception:
            log.warning("Could not save %s", self.path)

    def is_empty(self):
        return not (self.likes or self.dislikes or self.pets or self.favourites)

    # ---- learning ----
    def learn(self, tidy):
        """A whole sentence like 'i love pizza'. Returns ('like'|'dislike'|'pet'|'fav', details dict, is_new) or None."""
        if not self.enabled():
            return None
        found = _PET.match(tidy)
        if found:
            kind = found.group("k1") or found.group("k2") or found.group("k3")
            name = found.group("n")
            if name in ("a", "the", "my", "very", "so", "not", "old", "young", "big", "small", "cute", "good", "bad", "nice") or name in BLOCKED:
                return None
            return self._add_pet(kind, name)
        found = _FAV.match(tidy)
        if found:
            category, thing = found.group("cat"), _clean_thing(found.group("x"))
            if not acceptable(thing) or any(w in BLOCKED or w in PEOPLE for w in category.split()):
                return None
            return self._add_fav(category, thing)
        for pattern, kind in ((_LIKE, "like"), (_DISLIKE, "dislike")):
            found = pattern.match(tidy)
            if found:
                thing = _clean_thing(found.group("x"))
                if not acceptable(thing):
                    return None
                return self._add_item(kind, thing)
        return None

    def _add_item(self, kind, thing):
        with self._lock:
            mine, other = (self.likes, self.dislikes) if kind == "like" else (self.dislikes, self.likes)
            if thing in other:
                other.remove(thing)                  # you changed your mind
            if thing in mine:
                return kind, {"x": thing}, False
            mine.append(thing)
            del mine[:-MAX_ITEMS]
        self.save()
        return kind, {"x": thing}, True

    def _add_pet(self, kind, name):
        with self._lock:
            for pet in self.pets:
                if pet["name"] == name and pet["kind"] == kind:
                    return "pet", {"kind": kind, "name": name.capitalize()}, False
            self.pets.append({"kind": kind, "name": name})
            del self.pets[:-MAX_PETS]
        self.save()
        return "pet", {"kind": kind, "name": name.capitalize()}, True

    def _add_fav(self, category, thing):
        with self._lock:
            if self.favourites.get(category) == thing:
                return "fav", {"cat": category, "x": thing}, False
            self.favourites[category] = thing
            while len(self.favourites) > MAX_FAVS:
                self.favourites.pop(next(iter(self.favourites)))
        self.save()
        return "fav", {"cat": category, "x": thing}, True

    # ---- using it ----
    def mentions(self, tidy):
        """Does this sentence bring up something she knows? ('like'|'dislike'|'pet', details) or None."""
        if not self.enabled():
            return None
        padded = " %s " % tidy
        for pet in self.pets:
            if (" %s " % pet["name"]) in padded:
                return "pet", {"kind": pet["kind"], "name": pet["name"].capitalize()}
        for kind, items in (("like", self.likes), ("dislike", self.dislikes)):
            for thing in items:
                if (" %s " % thing) in padded or (" %ss " % thing) in padded:
                    return kind, {"x": thing}
        return None

    def forget(self, tidy):
        """'forget that i like pizza' / 'forget everything about me'. Returns 'all', 'one' or None."""
        if _FORGET_ALL.match(tidy) and ("about me" in tidy or "i told you" in tidy or "you know" in tidy or "you learned" in tidy
                                         or "you remember" in tidy or "i said" in tidy):
            self.clear()
            return "all"
        found = _FORGET_ONE.match(tidy)
        if not found:
            return None
        thing = _clean_thing(found.group("x"))
        removed = False
        with self._lock:
            for items in (self.likes, self.dislikes):
                if thing in items:
                    items.remove(thing)
                    removed = True
            for pet in list(self.pets):
                if pet["name"] == thing:
                    self.pets.remove(pet)
                    removed = True
            for category in [c for c, v in self.favourites.items() if v == thing or c == thing]:
                self.favourites.pop(category)
                removed = True
        if removed:
            self.save()
            return "one"
        return None

    def clear(self):
        with self._lock:
            self.likes, self.dislikes, self.pets, self.favourites = [], [], [], {}
        self.save()

    # ---- saying it ----
    @staticmethod
    def _list(items):
        items = list(items)
        if len(items) <= 1:
            return "".join(items)
        return ", ".join(items[:-1]) + " and " + items[-1]

    def summary_values(self):
        """Pieces for 'what do you know about me': only the ones she has."""
        values = {}
        if self.likes:
            values["likes"] = self._list(self.likes[-5:])
        if self.dislikes:
            values["dislikes"] = self._list(self.dislikes[-5:])
        if self.pets:
            values["pets"] = self._list("%s the %s" % (p["name"].capitalize(), p["kind"]) for p in self.pets[:3])
        if self.favourites:
            values["favs"] = self._list("%s is %s" % (c, v) for c, v in list(self.favourites.items())[-3:])
        return values
