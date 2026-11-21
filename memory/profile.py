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
import time

from core.logger import get_logger

log = get_logger("profile")

MAX_ITEMS = 30
MAX_PETS = 10
MAX_FAVS = 20
MAX_WORDS = 4
PETS = ("dog", "cat", "puppy", "kitten", "hamster", "rabbit", "parrot", "horse", "bird", "tortoise", "guinea pig", "goldfish", "snake",
        "lizard", "budgie", "ferret", "pony", "turtle", "gecko", "mouse", "rat", "hedgehog", "cockatiel", "chicken", "fish", "pig", "goat", "donkey",
        "spider", "chinchilla", "gerbil", "dove", "pigeon", "duck", "owl", "canary")
PET_SET = set(PETS) | {"guinea pig"}
PET_REPLY_SECONDS = 120.0        # after she asks "what's it called?", a bare name within this long is the pet's name
DEAD_WORDS = ("died", "dead", "passed away", "put down", "put to sleep", "killed", "ran over", "run over", "missing", "lost my")   # not hers to keep or joke about
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


NOT_NAMES = {"a", "an", "the", "my", "our", "very", "so", "not", "old", "young", "big", "small", "cute", "good", "bad", "nice", "new", "little", "lovely",
             "called", "named", "is", "are", "was", "were", "and", "but", "or", "who", "that", "which", "he", "she", "it", "they", "hes", "shes", "its", "theyre",
             "just", "also", "too", "now", "still", "always", "never", "really", "here", "there", "with", "from", "for", "in", "on", "at", "to", "of", "as", "like",
             "has", "have", "had", "does", "did", "will", "would", "can", "could", "loves", "likes", "keeps", "wants", "sleeps", "barks", "eats", "sits", "lies",
             "black", "white", "brown", "grey", "gray", "ginger", "orange", "golden", "tabby", "yellow", "red", "blue", "green", "pink", "spotty",
             "female", "male", "boy", "girl", "baby", "pet", "pets", "two", "three", "four", "five", "both", "all", "some", "one", "only", "other", "another",
             "yes", "no", "okay", "ok", "yeah", "yep", "nope", "thanks", "thank", "hello", "hi", "hey", "please", "sure", "fine", "well", "sorry", "maybe", "nothing",
             "nevermind", "whatever", "starling", "commander", "none", "dunno", "idk", "later", "stop", "cancel", "when", "what", "how", "why", "if", "then", "than", "because", "since", "while", "about", "again", "next", "me", "you", "us", "them", "him", "her"}
_PET_KIND_WORD = r"(?P<kind>[a-z]+(?: pig)?)"
_OWN = (r"(?:my|our|i have got|we have got|ive got|ive|i have|we have|weve got|weve|i got|we got|i own|we own|i adopted|we adopted|i rescued|we rescued|and my|and our|and a|and an|plus my)")
_PET_FIND = re.compile(r"\b(?P<own>" + _OWN + r") (?:(?:a|an|two|three|four|2|3|4|both|my|our|new|little|old|big|lovely|cute|young|tiny|rescue) )*" + _PET_KIND_WORD +
                       r"(?P<key> (?:is called|are called|is named|are named|called|named|names are|name is|s name is|s names are|s called))?(?= ?(?P<rest>[a-z ]{0,60}))")
_NAME_IS_MY = re.compile(r"\b(?P<name>[a-z]{2,15}) is my (?P<kind>[a-z]+(?: pig)?)\b")
_NAME_REPLY = re.compile(r"^(?:(?:his|her|its|their) names? (?:is|are|s)|(?:he|she|it|they)(?: is| are|s)? called|(?:he|she|it)s named|called|named|its|hes|shes)? ?(?P<rest>[a-z]{2,15}(?: and [a-z]{2,15})*)$")
_VERBISH = re.compile(r"(?:ed|ing|ly|ness)$")
_OWNING = ("i have got", "we have got", "ive got", "ive", "i have", "we have", "weve got", "weve", "i got", "we got", "i own", "we own", "i adopted", "we adopted", "i rescued", "we rescued")


def _kind_of(word):
    """'dogs' -> 'dog', 'puppies' -> 'puppy', 'mice' -> 'mouse'; None when it is not a pet."""
    word = (word or "").strip()
    if word in PET_SET:
        return word
    if word == "mice":
        return "mouse"
    for cut, add in (("ies", "y"), ("es", ""), ("s", "")):
        if word.endswith(cut) and word[:-len(cut)] + add in PET_SET:
            return word[:-len(cut)] + add
    if word.endswith("guinea pigs"):
        return "guinea pig"
    return None


def _good_name(name, bare=False):
    name = (name or "").strip()
    if not (2 <= len(name) <= 15) or not name.isalpha() or name in NOT_NAMES or name in BLOCKED or name in PEOPLE or _kind_of(name):
        return False
    if bare and (_VERBISH.search(name) or name.endswith("s")):          # 'my dog barked all night': 'barked' is not a name
        return False
    return True


def _names_in(rest, bare=False):
    """'milo and luna who are two' -> ['milo', 'luna'].  Stops at the first word that is not a name."""
    names, want = [], True
    for token in (rest or "").split():
        if want:
            if not _good_name(token, bare):
                break
            names.append(token)
            want = False
        elif token in ("and", "n"):
            want = True
        else:
            break
    return names[:4]


def find_pets(tidy):
    """Every pet a sentence tells about: [(kind, name)] with name '' when the pet has no name yet.
    'ive got a dog called rex and hes 3' -> rex the dog;  'we have two cats milo and luna' -> two;  'i have a dog' -> an unnamed dog."""
    if not tidy or len(tidy.split()) > 30 or any(w in tidy for w in DEAD_WORDS) or any(b in tidy.split() for b in BLOCKED):
        return []
    out, owning = [], False
    for found in _PET_FIND.finditer(tidy):
        kind = _kind_of(found.group("kind"))
        if not kind:
            continue
        keyword = bool(found.group("key"))
        owning = found.group("own") in _OWNING or (owning and found.group("own").startswith("and"))
        names = _names_in(found.group("rest"), bare=not keyword)
        if names:
            out += [(kind, n) for n in names]
        elif (found.group("own") in _OWNING or (owning and found.group("own").startswith("and"))) and not keyword:
            out.append((kind, ""))                           # 'i have a dog': she knows there is one, and may ask its name
    found = _NAME_IS_MY.search(tidy)
    if found and _kind_of(found.group("kind")) and _good_name(found.group("name")):
        out.append((_kind_of(found.group("kind")), found.group("name")))
    seen, unique = set(), []
    for kind, name in out:
        if (kind, name) not in seen:
            seen.add((kind, name))
            unique.append((kind, name))
    named = {k for k, n in unique if n}
    return [(k, n) for k, n in unique if n or k not in named][:MAX_PETS]


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
        self.extra_pets = []              # the other pets one sentence told her about (the first one is what learn() returns)
        self.pending_pet = None           # (kind, time): she asked what an unnamed pet is called
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
                     if isinstance(p, dict) and (p.get("name") or p.get("kind"))][:MAX_PETS]
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
        self.extra_pets = []
        pets = self._pets_from(tidy)
        if pets:
            results = [self._add_pet(kind, name) for kind, name in pets]
            first = next((r for r in results if r[2]), results[0])          # the first NEW one, else the first
            self.extra_pets = [r[1] for r in results if r is not first and r[2]]
            unnamed = [r for r in results if not r[1].get("name")]
            if unnamed and unnamed[0][2]:
                self.pending_pet = (unnamed[0][1]["kind"], time.monotonic())
            return first
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

    def _pets_from(self, tidy):
        """[(kind, name)]: the old exact sentence, the looser ones in find_pets, or a bare name answering 'what's it called?'."""
        found = _PET.match(tidy)
        if found:
            kind = found.group("k1") or found.group("k2") or found.group("k3")
            name = found.group("n")
            return [(kind, name)] if _good_name(name) else []
        pets = find_pets(tidy)
        if pets:
            return pets
        pending = self.pending_pet
        if pending and time.monotonic() - pending[1] <= PET_REPLY_SECONDS:
            found = _NAME_REPLY.match(tidy)
            if found:
                rest = found.group("rest")
                names = _names_in(rest)
                if names and len(names) * 2 - 1 == len(rest.split()):           # the whole reply was names
                    self.pending_pet = None
                    return [(pending[0], n) for n in names]
        return []

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
            if name:
                self.pets = [p for p in self.pets if not (p["kind"] == kind and not p["name"])]     # now she knows what the dog is called
            elif any(p["kind"] == kind for p in self.pets):
                return "pet", {"kind": kind, "name": ""}, False              # an unnamed dog when she already knows one
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
            if pet["name"] and (" %s " % pet["name"]) in padded:
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

    def remove(self, kind, key):
        """Forgets ONE thing for the 'What she knows about you' window. kind: 'like', 'dislike', 'pet' (key = the pet's name) or 'fav' (key = the category).
        True if it was there."""
        removed = False
        with self._lock:
            if kind == "like" and key in self.likes:
                self.likes.remove(key)
                removed = True
            elif kind == "dislike" and key in self.dislikes:
                self.dislikes.remove(key)
                removed = True
            elif kind == "pet":
                before = len(self.pets)
                self.pets = [p for p in self.pets if p["name"] != key]
                removed = len(self.pets) != before
            elif kind == "fav" and key in self.favourites:
                self.favourites.pop(key)
                removed = True
        if removed:
            self.save()
        return removed

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
            values["pets"] = self._list(("%s the %s" % (p["name"].capitalize(), p["kind"])) if p["name"] else "a %s" % p["kind"] for p in self.pets[:4])
        if self.favourites:
            values["favs"] = self._list("%s is %s" % (c, v) for c, v in list(self.favourites.items())[-3:])
        return values
