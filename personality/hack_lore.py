"""HACK LORE (0.96.3): her past, one chapter for every base she hacks for the East Orion Company.

Each economy is one part of the story (Industrial 5 chapters, Extraction 5, Agriculture 5, High Tech 4, Military 5, Tourist 4 = 28). After
a hack the chapter for that kind of base is told, in order, whatever her mood. When all 28 are heard she tells the finale, once.
What you have heard is saved in data/hack_lore.json. The words are in voicepacks/default/hack_lore.json.
"""
import json
import os
import re
import time

from core.identity import assistant_name, personalise
from core.logger import get_logger

log = get_logger("hack_lore")

GROUPS = ("Industrial", "Extraction", "Agriculture", "High Tech", "Military", "Tourist")
_REPLAY = re.compile(r"^(?:replay|repeat|say again|tell again)\s+(?:the\s+)?(?:last\s+)?(?:hack\s+)?(?:chapter|memory|story)$")
_PROGRESS = re.compile(r"^(?:how many|which)\s+(?:hack\s+)?(?:chapters|memories)\b.*$")


def key_of(group):
    return "HackLore_%s" % str(group).replace(" ", "_")


class HackLore:
    def __init__(self, speech_provider, dialogue, settings, path=None, clock=time.monotonic):
        self.speech_provider = speech_provider
        self.dialogue = dialogue
        self.settings = settings
        self.path = path
        self.clock = clock
        self.told = {}                 # group -> chapters told
        self.finale = False
        self.last = None
        self._load()

    # ---- remembering ----
    def _load(self):
        if self.path is None:
            return
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            self.told = {str(k): int(v) for k, v in (data.get("told") or {}).items()}
            self.finale = bool(data.get("finale"))
            self.last = data.get("last")
        except FileNotFoundError:
            pass
        except (OSError, ValueError, AttributeError, TypeError):
            log.warning("Could not read %s; the story starts again from the beginning", self.path)

    def _save(self):
        if self.path is None:
            return
        try:
            temp = str(self.path) + ".tmp"
            with open(temp, "w", encoding="utf-8") as handle:
                json.dump({"told": self.told, "finale": self.finale, "last": self.last}, handle)
            os.replace(temp, self.path)
        except OSError:
            log.exception("Could not save the hack story")

    # ---- the words ----
    def _dialogue(self):
        return self.dialogue() if callable(self.dialogue) else self.dialogue

    def _lines(self, key):
        d = self._dialogue()
        return [l.text for l in (d.lines.get(key, []) if d is not None else [])]

    def chapters(self, group):
        return self._lines(key_of(group))

    def total(self):
        return sum(len(self.chapters(g)) for g in GROUPS)

    def heard(self):
        return sum(min(self.told.get(g, 0), len(self.chapters(g))) for g in GROUPS)

    def _say(self, text):
        text = personalise(text.replace("{name}", assistant_name(self.settings)), self.settings)
        speech = self.speech_provider() if callable(self.speech_provider) else self.speech_provider
        if speech is not None and self.settings.get("speech.enabled", True):
            speech.say(text=text, priority="normal", event_name="hack.lore")
        return text

    def _pick(self, key):
        lines = self._lines(key)
        if not lines:
            return None
        return lines[int(self.clock() * 1000) % len(lines)]

    def pick_group(self):
        """The part with the fewest chapters told that still has some left (used when the base's kind is unknown)."""
        open_groups = [g for g in GROUPS if self.told.get(g, 0) < len(self.chapters(g))]
        return min(open_groups, key=lambda g: self.told.get(g, 0)) if open_groups else None

    # ---- telling ----
    def tell(self, group=None):
        """Tell the next chapter for this kind of base. Returns what she said (or None if there is nothing to say)."""
        if group not in GROUPS:
            group = self.pick_group() or (GROUPS[0] if self.chapters(GROUPS[0]) else None)
        if group is None:
            return None
        chapters = self.chapters(group)
        done = self.told.get(group, 0)
        if done >= len(chapters):
            other = self.pick_group()
            if other is not None:
                return self.tell(other)
            note = self._pick("HackLore_Done")
            return self._say(note) if note else None
        text = chapters[done]
        self.told[group] = done + 1
        self.last = text
        intro = self._pick("HackLore_Intro") if done == 0 and self.heard() == 0 else None
        said = self._say("%s || %s" % (intro, text) if intro else text)
        if self.heard() >= self.total() and not self.finale:
            self.finale = True
            ending = self._lines("HackLore_Finale")
            if ending:
                said += " " + self._say(" || ".join(ending))
        self._save()
        return said

    def replay(self):
        if not self.last:
            return None
        return self._say(self.last)

    def progress_line(self):
        return "She has told %d of %d memories." % (self.heard(), self.total())

    # ---- voice ----
    def try_handle(self, text):
        said = re.sub(r"[^a-z ]", " ", str(text or "").lower())
        said = " ".join(said.split())
        if _REPLAY.match(said):
            return self.replay() or "There is no chapter to replay yet."
        if _PROGRESS.match(said):
            line = self.progress_line()
            self._say(line.replace("She has", "I have").replace("memories", "memories so far"))
            return line
        return None
