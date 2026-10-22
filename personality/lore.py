"""
LORE - her back story, told a chapter at a time.

Ask "who are you", "what are you", "tell me about yourself", "who made you" or "tell me more" and she tells the next
chapter you have not heard. How much she tells depends on how much she likes you (her mood):
    calm (Neutral)       the company brochure version (Lore_L1)
    Friendly             ... and the real story (Lore_L2)
    Close                ... and the personal bits (Lore_L3)
    bad mood             the horrible things that happened to her, told as dark comedy (Lore_Dark)
Once she has told everything she is allowed to, she says there is more if you are kind to her.
Which chapters you have heard is saved in data/lore.json, so she never repeats herself until she has run out.
All the words are in voicepacks/default/lore.json.
"""
import json
import os
import time

from core.identity import assistant_name, personalise
from core.logger import get_logger
from personality.mood_engine import effective_mood

log = get_logger("lore")

BAD_MOODS = ("Sarcastic", "Frustrated", "Upset")
TIERS = {"": ["Lore_L1"], "Neutral": ["Lore_L1"], "Friendly": ["Lore_L1", "Lore_L2"], "Close": ["Lore_L1", "Lore_L2", "Lore_L3"],
         "Infatuated": ["Lore_L1", "Lore_L2", "Lore_L3"]}
ALL_GOOD = ["Lore_L1", "Lore_L2", "Lore_L3"]
RECENT_SECONDS = 300.0


class LoreTeller:
    def __init__(self, speech, dialogue, settings, path=None, clock=time.monotonic, rng=None):
        import random
        self.speech = speech
        self.dialogue = dialogue
        self.settings = settings
        self.path = path
        self.clock = clock
        self.rng = rng or random.Random()
        self.heard = set()
        self.last_told = None
        self._load()

    # ---- remembering what you have heard ----
    def _load(self):
        if self.path is None:
            return
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            self.heard = {str(x) for x in data.get("heard", [])}
        except FileNotFoundError:
            pass
        except (OSError, ValueError, AttributeError):
            log.warning("Could not read %s; she will start the story from the beginning", self.path)

    def _save(self):
        if self.path is None:
            return
        try:
            tmp = str(self.path) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump({"heard": sorted(self.heard)}, handle)
            os.replace(tmp, self.path)
        except OSError:
            log.exception("Could not save which chapters you have heard")

    def forget(self):
        self.heard.clear()
        self._save()

    # ---- telling ----
    def recent(self):
        return self.last_told is not None and self.clock() - self.last_told <= RECENT_SECONDS

    def _mood(self):
        if self.settings.get("personality.style", "personality") != "personality":
            return ""
        return effective_mood(self.settings) or "Neutral"

    def _chapters(self, key):
        allow = bool(self.settings.get("speech.allow_mature", False))
        return [(i, line) for i, line in enumerate(self.dialogue.lines.get(key, [])) if allow or not line.mature]

    def _next_unheard(self, keys):
        for key in keys:
            for index, line in self._chapters(key):
                if "%s:%d" % (key, index) not in self.heard:
                    return key, index, line
        return None

    def _say(self, text):
        text = personalise(text.replace("{name}", assistant_name(self.settings)), self.settings)
        if self.speech is not None and self.settings.get("speech.enabled", True):
            self.speech.say(text=text, priority="normal", event_name="lore")
        self.last_told = self.clock()
        return text

    def _pick(self, key):
        line = self.dialogue.pick(key, "", bool(self.settings.get("speech.allow_mature", False)), False)
        return line.text if line is not None else None

    def tell(self):
        """Say the next chapter this mood allows. Returns what she said, or None if there is no lore at all."""
        mood = self._mood()
        bad = mood in BAD_MOODS
        keys = ["Lore_Dark"] if bad else TIERS.get(mood, TIERS["Neutral"])
        found = self._next_unheard(keys)
        if found is not None:
            key, index, line = found
            self.heard.add("%s:%d" % (key, index))
            self._save()
            return self._say(line.text)
        # nothing new to tell in this mood
        if bad:
            note = self._pick("Lore_DarkDone")
        elif self._next_unheard([k for k in ALL_GOOD if k not in keys]) is not None:
            note = self._pick("Lore_Locked")           # there IS more, but she doesn't like you enough yet
        else:
            note = self._pick("Lore_Done")
            replay = [line for k in keys for _i, line in self._chapters(k)]
            if note and replay:
                return self._say("%s || %s" % (note, self.rng.choice(replay).text))
        if not note:
            note = self._pick("Lore_Missing")
        return self._say(note) if note else None
