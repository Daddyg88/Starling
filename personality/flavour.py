"""
Flavour: the little bits of personality sprinkled on top of her normal lines.

  * pet names   "Docked, Commander."  ->  "Docked, Sweetheart."
  * remarks     a short extra comment after the line, e.g. "Docked. || Try not to scratch the paint."

What she says depends on her mood:
    Neutral            calm, professional, dry remarks
    Friendly / Close   cute remarks and sweet pet names
    Sarcastic          snide remarks (and a little swearing if strong language is on)
    Frustrated         snide and sweary remarks
    Friendly or Close + "Flirty and naughty" switched on (dashboard)   cheeky innuendo
    Rich (see below)   if you carry more than `personality.affection_credits` of exobiology data
                       she gets very affectionate

SAFETY: critical warnings are never touched, and nothing is added in "info" style.
All the words live in voicepacks/default/personality.json - edit them freely.
"""

import random
import re

from personality.mood_engine import effective_mood
import time

from core.identity import sex_label

REMARK_CHANCE = {"off": 0.0, "rare": 0.08, "sometimes": 0.18, "often": 0.32}
PET_NAME_CHANCE = 0.35
REMARK_COOLDOWN_SECONDS = 40
MAX_LINE_CHARS = 150            # long lines (exobiology numbers etc.) are left alone
_COMMANDER = re.compile(r"\bCommander\b(?!\s+[A-Z])")
GOOD_MOODS = ("Friendly", "Close")
BAD_MOODS = ("Sarcastic", "Frustrated")
DARK_HUMOUR_CHANCE = 0.2          # of the remarks she makes, about one in five is gallows humour


class Flavour:
    def __init__(self, dialogue, settings, carried_provider=None, rng=None, clock=time.monotonic):
        self.dialogue = dialogue
        self.settings = settings
        self.carried_provider = carried_provider or (lambda: 0)
        self.rng = rng or random.Random()
        self.clock = clock
        self._last_remark = None

    # ---- what is she like right now? ----
    def active(self):
        return self.settings.get("personality.style", "personality") == "personality"

    def rich(self):
        try:
            limit = float(self.settings.get("personality.affection_credits", 500000000))
            return limit > 0 and float(self.carried_provider() or 0) >= limit
        except (TypeError, ValueError):
            return False

    def innuendo_on(self, mood):
        """The dashboard switch is on, and she is Friendly or Close (flirty), Sarcastic or Frustrated (rude), or calm and rich-in-cargo."""
        if not self.settings.get("personality.innuendo", False):
            return False
        return mood in ("Close", "Friendly", "Sarcastic", "Frustrated") or (self.rich() and mood == "Neutral")

    def _innuendo_chance(self, mood, close_chance):
        """Cheekiest when she is Close; less often when Friendly, and when she is in a bad mood."""
        if mood == "Close":
            return close_chance
        return close_chance * (0.6 if mood == "Friendly" else 0.5)

    def _dark_remark(self, mood):
        """A little gallows humour, in every mood. Uses the mood's own lines when there are some."""
        if not self.settings.get("personality.dark_humour", True):
            return None
        mature = self._mature()
        key = "Remark_Dark_%s" % mood
        pool = self.dialogue.pool(key, "", mature, False)
        if pool and self.rng.random() < 0.6:
            return self._pick(key)
        return self._pick("Remark_Dark")

    def _mature(self):
        return bool(self.settings.get("speech.allow_mature", False))

    def _pick(self, key):
        # "Male" / "Female" pulls in the Key_Male / Key_Female lines too (handsome, beautiful...)
        line = self.dialogue.pick(key, sex_label(self.settings), self._mature(), False)
        return line.text if line is not None else None

    # ---- pet names ----
    def _pet_name(self, mood):
        if self.innuendo_on(mood) and self.rng.random() < self._innuendo_chance(mood, 0.4):
            name = self._pick("PetName_Naughty_Grumpy" if mood in BAD_MOODS else "PetName_Naughty")
            if name:
                return name
        if self.rich() and (mood != "Frustrated" or self.rng.random() < 0.4):
            return self._pick("PetName_Affection")
        if mood == "Neutral":
            return self._pick("PetName_Neutral")
        if mood in GOOD_MOODS:
            return self._pick("PetName_Cute")
        if mood == "Frustrated" and self._mature() and self.rng.random() < 0.5:
            return self._pick("PetName_Sweary")
        return self._pick("PetName_Snide")

    # ---- remarks ----
    def _remark(self, mood):
        if self.innuendo_on(mood) and self.rng.random() < self._innuendo_chance(mood, 0.55):
            remark = self._pick("Remark_Innuendo_Grumpy" if mood in BAD_MOODS else "Remark_Innuendo")
            if remark:
                return remark
        if self.rng.random() < DARK_HUMOUR_CHANCE:
            remark = self._dark_remark(mood)
            if remark:
                return remark
        if self.rich() and (mood != "Frustrated" or self.rng.random() < 0.4):
            return self._pick("Remark_Affection")
        if mood == "Neutral":
            return self._pick("Remark_Neutral")
        if mood in GOOD_MOODS:
            if mood == "Close" and self.rng.random() < 0.3:
                return self._pick("Remark_Affection") if self.rich() else self._pick("Remark_Cute")
            return self._pick("Remark_Cute")
        sweary_chance = 0.6 if mood == "Frustrated" else 0.3
        if self._mature() and self.rng.random() < sweary_chance:
            return self._pick("Remark_Sweary")
        return self._pick("Remark_Snide")

    def rename(self, text, always=False):
        """Maybe swap "Commander" for a pet name (no remarks). always=True skips the dice roll."""
        if not self.active() or not text or not self.settings.get("personality.pet_names", True):
            return text
        if not _COMMANDER.search(text):
            return text
        chance = 0.7 if self.rich() else PET_NAME_CHANCE
        if always or self.rng.random() < chance:
            name = self._pet_name(effective_mood(self.settings))
            if name:
                return _COMMANDER.sub(name, text, count=1)
        return text

    # ---- the one call the speaker makes ----
    def apply(self, text, priority="normal"):
        """Return `text`, possibly with a pet name and/or a remark added."""
        if priority == "critical" or not self.active() or not text:
            return text
        mood = effective_mood(self.settings)
        text = self.rename(text)

        if "||" in text or len(text) > MAX_LINE_CHARS or "{" in text:
            return text
        chance = REMARK_CHANCE.get(str(self.settings.get("personality.remarks", "sometimes")).lower(), 0.18)
        if self.rich():
            chance = min(0.6, chance * 2)
        now = self.clock()
        if chance > 0 and (self._last_remark is None or now - self._last_remark >= REMARK_COOLDOWN_SECONDS):
            if self.rng.random() < chance:
                remark = self._remark(mood)
                if remark:
                    self._last_remark = now
                    text = "%s || %s" % (text.rstrip(), remark)
        return text
