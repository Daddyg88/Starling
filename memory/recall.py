"""
RECALL - how she talks about what she remembers. Used at login and for "what do you remember?".
Her words live in voicepacks/default/memory.json. This file only picks facts and fills in the blanks.
"""
import re

from core.identity import personalise
from core.logger import get_logger
from personality.mood_engine import effective_mood

log = get_logger("memory")

ASK = re.compile(r"\b(what do you remember|what can you remember|tell me (what|your) (you )?remember|"
                 r"tell me your memories|what have you remembered|what do you recall)\b")
FORGET_ALL = re.compile(r"\b(forget everything|forget all (of )?your memories|wipe your memory)\b")
# the kinds of memory she may bring up by herself, in the order she likes them
STORY_KINDS = ("record:longest_jump", "record:biggest_organic_sale", "record:biggest_exploration_sale",
               "death", "big_mission", "first_species")
REST_HOURS = 6          # a memory she has just mentioned is left alone for this long (asking her "what do you remember" ignores it)
SAYINGS = {"record:": "Memory_Record", "death": "Memory_Death", "big_mission": "Memory_Mission", "first_species": "Memory_First"}


def spoken_summary(memory):
    """What she says out loud for a memory. A mission memory keeps only the payout ('a mission worth 5.1 million credits')
    when the mission title after the colon is long; a short title is kept."""
    text = str(memory.get("summary") or "")
    if memory.get("memory_type") == "big_mission" and ":" in text:
        head, title = text.split(":", 1)
        if len(title.strip()) > 30:
            text = head.strip()
    return text


class _Safe(dict):
    def __missing__(self, key):
        return "?"


_PET_NOUN = (r"(?:dog|cat|puppy|kitten|hamster|rabbit|parrot|horse|bird|tortoise|guinea pig|goldfish|snake|lizard|budgie|ferret|pony|turtle|gecko|mouse|rat|hedgehog|"
             r"cockatiel|chicken|fish|pig|goat|donkey|spider|chinchilla|gerbil|dove|pigeon|duck|owl|canary)")
_PETS_PLURAL = _PET_NOUN + r"(?:s|es|ies)?|pets?|mice"
_ASK_PETS = re.compile(r"^(?:(?:do you|can you|could you) (?:still )?(?:remember|know|recall)|(?:tell me|talk to me) about|what do you (?:remember|know) about|remember|"
                       r"have i (?:told|mentioned)(?: to)? you about|what about|how (?:is|are|s)|hows) (?:my |our |the )?(?P<what>" + _PETS_PLURAL + r")(?: names?| called)?(?: again)?$|"
                       r"^what (?:pets|animals) do i have$|^do i have (?:any |a |an )?(?P<have>" + _PETS_PLURAL + r")$|^(?:what|which) (?P<which>" + _PETS_PLURAL + r") do i have$")
_ASK_PET_NAME = re.compile(r"^(?:who is|whos|who was|do you (?:still )?(?:remember|know)|remember|tell me about|what do you (?:remember|know) about|how is|how are|hows|how s) (?P<n>[a-z]{2,15})$")
_ASK_LIKE_ONE = re.compile(r"^(?:do you (?:remember|know) (?:if |whether )?)?do i (?P<verb>like|love|enjoy|hate|dislike) (?P<x>[a-z ]{2,30})$|"
                           r"^(?:do you (?:remember|know)|did i (?:tell|say to) you) (?:if |whether )?i (?P<verb2>like|love|enjoy|hate|dislike) (?P<x2>[a-z ]{2,30})$")
_ASK_LIKES = re.compile(r"^(?:do you (?:remember|know)|can you tell me|tell me) what (?:things )?i (?P<verb>like|love|enjoy|hate|dislike|am into)$|^what are my (?P<verb2>likes|dislikes)$")
_ASK_ME = re.compile(r"^(?:what do you (?:remember|know) (?:about|of) me|what have i told you(?: about myself)?|tell me what you (?:remember|know) about me|"
                     r"what (?:else )?do you (?:remember|know)(?: about me)?|do you remember anything about me|do you know anything about me)$")
_ASK_FACTS = (
    (re.compile(r"\b(?:longest jump|furthest jump|biggest jump)\b"), "record:longest_jump"),
    (re.compile(r"\b(?:biggest|best|largest) (?:organic|biological|exobiology|bio) sale\b"), "record:biggest_organic_sale"),
    (re.compile(r"\b(?:biggest|best|largest) (?:exploration|cartography|data) sale\b"), "record:biggest_exploration_sale"),
    (re.compile(r"\b(?:biggest|best|largest|most expensive|richest) mission\b"), "big_mission"),
    (re.compile(r"\b(?:last|latest|most recent) (?:time )?(?:i|we) (?:died|was destroyed|were destroyed|got destroyed|blew up|exploded)\b|\bwhen did i (?:last )?(?:die|get destroyed)\b"), "death"),
    (re.compile(r"\bfirst (?:species|organism|sample|thing i sampled|plant)\b"), "first_species"),
)
_ASK_FACT_LEAD = re.compile(r"^(?:do you (?:still )?(?:remember|know)|can you (?:remember|tell me)|what (?:was|is|were)|tell me|remind me)\b")
_ASK_HOURS = re.compile(r"^(?:how (?:long|many hours) (?:have|has) (?:we|i)(?: been)? (?:been )?(?:playing|flying|together|travelling|travelled)(?: together)?|how long have we known each other|how many hours have we (?:flown|played|spent)(?: together)?)$")
_ASK_DEATHS = re.compile(r"^how many times (?:have i|did i|have we|did we) (?:died|die|been destroyed|get destroyed|got destroyed|blown up)$")


def _kind_name(word):
    word = word or ""
    for cut, add in (("ies", "y"), ("es", ""), ("s", "")):
        if word.endswith(cut) and re.fullmatch(_PET_NOUN, word[:-len(cut)] + add):
            return word[:-len(cut)] + add
    return "mouse" if word == "mice" else word


class MemoryRecall:
    def __init__(self, store, dialogue, settings, speech=None, profile=None, habits=None):
        self.store = store
        self.dialogue = dialogue
        self.settings = settings
        self.speech = speech
        self.profile = profile        # memory/profile.py: pets, likes, favourites (the app sets this after it is built)
        self.habits = habits          # memory/habits.py: the station you dock at most

    def enabled(self):
        return bool(self.settings.get("memory.enabled", True))

    def _say(self, key, mood, values):
        allow = bool(self.settings.get("speech.allow_mature", False))
        line = self.dialogue.pick(key, mood, allow, False)
        if line is None:
            return None
        text = personalise(line.text.format_map(_Safe(values)), self.settings)
        return text[:1].upper() + text[1:] if text[:1].islower() else text        # a line that starts with the memory ("the first time you...") still starts with a capital

    def _mood(self):
        if self.settings.get("personality.style", "personality") != "personality":
            return ""
        return effective_mood(self.settings) or ""

    def _frame(self, memory):
        kind = memory["memory_type"]
        for prefix, key in SAYINGS.items():
            if kind.startswith(prefix):
                return key
        return "Memory_Record"

    def login_line(self):
        """One memory for the login greeting (the one she has mentioned least), or None."""
        if not (self.enabled() and self.settings.get("memory.recall_at_login", True)):
            return None
        found = self.store.least_mentioned(STORY_KINDS, 1, rest_hours=REST_HOURS)       # not the one she brought up a moment ago
        if not found:
            return None
        memory = found[0]
        text = self._say(self._frame(memory) + "_Login", self._mood(), {"memory": spoken_summary(memory), "system": memory["system_name"] or "there"})
        if text:
            self.store.mentioned(memory["id"])
        return text

    # ---- what you told her ----
    def _profile_on(self):
        return self.profile is not None and bool(self.settings.get("brain.profile", True))

    def _told_parts(self, mood):
        """What you have told her, as spoken pieces: likes, dislikes, pets, favourites."""
        values = self.profile.summary_values() if self._profile_on() else {}
        parts = []
        for name in ("Likes", "Dislikes", "Pets", "Favs"):
            if name.lower() in values:
                parts.append(self._say("Profile_Sum_" + name, mood, values))
        return [p for p in parts if p]

    def _pet_text(self, pet):
        return ("%s the %s" % (pet["name"].capitalize(), pet["kind"])) if pet["name"] else "a %s" % pet["kind"]

    def _pets(self, tidy, mood):
        """'how is my dog', 'do you remember my cats', 'do i have a dog', 'what pets do i have', 'who is rex'."""
        found = _ASK_PETS.match(tidy)
        pets = list(getattr(self.profile, "pets", []) or [])
        if found:
            word = found.group("what") or found.group("have") or found.group("which") or "pets"
            kind = None if word in ("pet", "pets") else _kind_name(word)
            same = [p for p in pets if kind is None or p["kind"] == kind]
            asked_have = bool(found.group("have") or found.group("which") or tidy.startswith("what pets") or tidy.startswith("what animals"))
            if not same:
                if kind is None or not pets:
                    return self._say("Profile_NoPet", mood, {}) or "You haven't told me about a pet yet."
                return self._say("Recall_PetOther", mood, {"kind": kind, "pets": self._list([self._pet_text(p) for p in pets[:4]])})
            named = [p for p in same if p["name"]]
            how = bool(re.match(r"^(?:how is|how are|hows|how s)", tidy))
            if not named:
                return self._say("Recall_PetNoName", mood, {"kind": same[-1]["kind"]})
            if how and len(named) == 1:
                return self._say("Recall_PetHow", mood, {"name": named[0]["name"].capitalize(), "kind": named[0]["kind"]})
            return self._say("Recall_PetsAre" if not asked_have else "Recall_HavePets", mood,
                             {"pets": self._list([self._pet_text(p) for p in same[:4]]), "count": len(same)})
        found = _ASK_PET_NAME.match(tidy)
        if found:
            name = found.group("n")
            for pet in pets:
                if pet["name"] == name:
                    key = "Recall_PetHow" if re.match(r"^(?:how is|how are|hows|how s)", tidy) else "Recall_PetNamed"
                    return self._say(key, mood, {"name": name.capitalize(), "kind": pet["kind"]})
        return None

    @staticmethod
    def _list(items):
        items = list(items)
        return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]

    def _likes(self, tidy, mood):
        found = _ASK_LIKE_ONE.match(tidy)
        if found:
            thing = re.sub(r"^(?:the |a |an |some |any )", "", (found.group("x") or found.group("x2") or "").strip())
            likes, dislikes = getattr(self.profile, "likes", []), getattr(self.profile, "dislikes", [])
            plain = thing[:-1] if thing.endswith("s") else thing
            if thing in likes or plain in likes:
                return self._say("Recall_LikeYes", mood, {"x": thing if thing in likes else plain})
            if thing in dislikes or plain in dislikes:
                return self._say("Recall_LikeNo", mood, {"x": thing if thing in dislikes else plain})
            return self._say("Recall_LikeUnknown", mood, {"x": thing})
        found = _ASK_LIKES.match(tidy)
        if found:
            verb = found.group("verb") or found.group("verb2") or ""
            values = self.profile.summary_values()
            dislike = verb.startswith(("hate", "dislike"))
            if dislike and "dislikes" in values:
                return self._say("Profile_Sum_Dislikes", mood, values)
            if not dislike and "likes" in values:
                return self._say("Profile_Sum_Likes", mood, values)
            return self._say("Profile_NoDislikes" if dislike else "Profile_NoLikes", mood, {})
        return None

    # ---- things that happened ----
    def _fact(self, tidy, mood):
        """'what's my longest jump', 'do you remember my biggest sale', 'when did i last die', 'how long have we been playing'."""
        if _ASK_HOURS.match(tidy):
            hours = (self.store.stats().get("hours_together", 0) or 0)
            if hours >= 0.1:
                return self._say("Memory_Hours", mood, {"hours": ("%.1f" % hours).rstrip("0").rstrip(".")})
            return self._say("Memory_Empty", mood, {})
        if _ASK_DEATHS.match(tidy):
            count = self.store.stats().get("times_destroyed", 0)
            return self._say("Memory_Destroyed", mood, {"count": count}) if count else self._say("Memory_NoDeaths", mood, {})
        if not _ASK_FACT_LEAD.match(tidy) and not re.search(r"\bmy\b", tidy):
            return None
        for pattern, kind in _ASK_FACTS:
            if pattern.search(tidy):
                rows = self.store.by_kind(kind, 1)
                if not rows:
                    return self._say("Memory_NoNote", mood, {})
                memory = rows[0]
                return self._say(self._frame(memory) + "_Ask", mood, {"memory": spoken_summary(memory), "system": memory["system_name"] or "there"})
        return None

    def _personal(self, tidy, mood):
        """Everything asked about you: pets, likes, 'what do you know about me', and the moments she kept."""
        if self._profile_on():
            for ask in (self._pets, self._likes):
                reply = ask(tidy, mood)
                if reply:
                    return reply
        if self.enabled():
            reply = self._fact(tidy, mood)
            if reply:
                return reply
        if _ASK_ME.match(tidy):
            return self.answer(with_profile=True)
        return None

    def _favourite_station(self, mood):
        try:
            favourite = self.habits.favourite_station() if self.habits is not None else None
        except Exception:
            return None
        return self._say("Memory_Favourite", mood, {"station": favourite[0], "count": favourite[1]}) if favourite else None

    def answer(self, with_profile=True):
        """The full answer to 'what do you remember?': what you told her (pets, likes, favourites), then the moments she kept and the place you dock at most."""
        mood = self._mood()
        stats = self.store.stats()
        found = self.store.least_mentioned(STORY_KINDS, 3) if self.enabled() else []
        parts = self._told_parts(mood)[:3] if self._profile_on() else []          # what you told her first, then the moments
        hours = stats.get("hours_together", 0) or 0
        if hours >= 0.1:
            parts.append(self._say("Memory_Hours", mood, {"hours": ("%.1f" % hours).rstrip("0").rstrip(".")}))
        for memory in found:
            parts.append(self._say(self._frame(memory) + "_Ask", mood,
                                   {"memory": spoken_summary(memory), "system": memory["system_name"] or "there"}))
            self.store.mentioned(memory["id"])
        if stats.get("times_destroyed"):
            parts.append(self._say("Memory_Destroyed", mood, {"count": stats["times_destroyed"]}))
        favourite = self._favourite_station(mood)
        if favourite:
            parts.append(favourite)
        parts = [p for p in parts if p]
        if not parts:
            return self._say("Memory_Empty", mood, {}) or "I haven't got much yet, Commander. Give me time."
        return " || ".join(parts) if len(parts) > 1 else parts[0]

    def try_handle(self, text):
        """Voice commands. Returns what she said, or None if this wasn't about memory."""
        lowered = (text or "").lower()
        tidy = None
        try:
            from personality.smalltalk import clean
            tidy = re.sub(r"^(?:hey |hi |ok |okay |oi )?(?:starling )", "", clean(text or "")) or None
        except Exception:
            tidy = None
        personal = None
        if tidy and not FORGET_ALL.search(lowered):
            try:
                personal = self._personal(tidy, self._mood())
            except Exception:
                log.exception("A personal memory question failed")
        if personal:
            reply = personal
        elif FORGET_ALL.search(lowered):
            reply = self._say("Memory_ForgetHow", self._mood(), {}) or "You can clear my memory on the Memory page of the dashboard."
        elif ASK.search(lowered):
            reply = self.answer()
        else:
            return None
        if self.speech is not None:
            self.speech.say(text=reply, priority="normal", event_name="memory.recall")
        return reply
