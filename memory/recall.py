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
SAYINGS = {"record:": "Memory_Record", "death": "Memory_Death", "big_mission": "Memory_Mission", "first_species": "Memory_First"}


class _Safe(dict):
    def __missing__(self, key):
        return "?"


class MemoryRecall:
    def __init__(self, store, dialogue, settings, speech=None):
        self.store = store
        self.dialogue = dialogue
        self.settings = settings
        self.speech = speech

    def enabled(self):
        return bool(self.settings.get("memory.enabled", True))

    def _say(self, key, mood, values):
        allow = bool(self.settings.get("speech.allow_mature", False))
        line = self.dialogue.pick(key, mood, allow, False)
        if line is None:
            return None
        return personalise(line.text.format_map(_Safe(values)), self.settings)

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
        found = self.store.least_mentioned(STORY_KINDS, 1)
        if not found:
            return None
        memory = found[0]
        text = self._say(self._frame(memory) + "_Login", self._mood(), {"memory": memory["summary"], "system": memory["system_name"] or "there"})
        if text:
            self.store.mentioned(memory["id"])
        return text

    def answer(self):
        """The full answer to 'what do you remember?'."""
        mood = self._mood()
        stats = self.store.stats()
        found = self.store.least_mentioned(STORY_KINDS, 3) if self.enabled() else []
        parts = []
        hours = stats.get("hours_together", 0) or 0
        if hours >= 0.1:
            parts.append(self._say("Memory_Hours", mood, {"hours": ("%.1f" % hours).rstrip("0").rstrip(".")}))
        for memory in found:
            parts.append(self._say(self._frame(memory) + "_Ask", mood,
                                   {"memory": memory["summary"], "system": memory["system_name"] or "there"}))
            self.store.mentioned(memory["id"])
        if stats.get("times_destroyed"):
            parts.append(self._say("Memory_Destroyed", mood, {"count": stats["times_destroyed"]}))
        parts = [p for p in parts if p]
        if not parts:
            return self._say("Memory_Empty", mood, {}) or "I haven't got much yet, Commander. Give me time."
        return " || ".join(parts) if len(parts) > 1 else parts[0]

    def try_handle(self, text):
        """Voice commands. Returns what she said, or None if this wasn't about memory."""
        lowered = (text or "").lower()
        if FORGET_ALL.search(lowered):
            reply = self._say("Memory_ForgetHow", self._mood(), {}) or "You can clear my memory on the Memory page of the dashboard."
        elif ASK.search(lowered):
            reply = self.answer()
        else:
            return None
        if self.speech is not None:
            self.speech.say(text=reply, priority="normal", event_name="memory.recall")
        return reply
