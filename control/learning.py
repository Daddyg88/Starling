"""
SPEECH LEARNING - she gets better at understanding YOU.

Be clear about what this is: it does NOT retrain the speech-to-text model (that needs hours of recordings and a
powerful PC). What it does is learn the way the recogniser tends to mis-hear you.

When a sentence is not an exact command but is very close to one, she already runs it (the "fuzzy" match). Each time
that happens she makes a note: "when I hear 'lower the land gear' it turns out to mean 'lower gear'". After you have
been understood that way twice, she remembers it as one of YOUR phrases and from then on understands it instantly
and exactly. The list is kept in data/voice_learning.json (plain text; delete the file to start again).

Safety: only the normal fuzzy matches are learned (never the "strict" big actions like jumping), and a phrase that
could mean two different things is never promoted.
"""
import json
import os
import tempfile
import threading

from core.logger import get_logger

log = get_logger("learning")

PROMOTE_AFTER = 2          # times it must be understood the same way before she trusts it
MAX_ENTRIES = 600


class VoiceLearning:
    def __init__(self, path, enabled=lambda: True):
        self.path = path
        self.enabled = enabled
        self._lock = threading.Lock()
        self.seen = {}                 # heard sentence -> {canonical sentence: count}
        self._dirty = False
        self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            seen = data.get("heard", {}) if isinstance(data, dict) else {}
            for heard, options in seen.items():
                if isinstance(options, dict):
                    self.seen[str(heard)] = {str(k): int(v) for k, v in options.items() if isinstance(v, (int, float))}
        except FileNotFoundError:
            pass
        except Exception:
            log.warning("Could not read %s; starting a fresh learning list.", self.path)

    def learned(self, heard):
        """The exact sentence this mis-hearing has come to mean, or None."""
        if not self.enabled():
            return None
        options = self.seen.get(heard)
        if not options:
            return None
        ranked = sorted(options.items(), key=lambda kv: -kv[1])
        top = ranked[0]
        if top[1] >= PROMOTE_AFTER and (len(ranked) == 1 or ranked[1][1] < top[1]):
            return top[0]
        return None

    def note(self, heard, sentence):
        """She understood `heard` as `sentence` by a close match."""
        if not self.enabled() or heard == sentence or len(heard) < 4:
            return
        with self._lock:
            options = self.seen.setdefault(heard, {})
            options[sentence] = options.get(sentence, 0) + 1
            if len(self.seen) > MAX_ENTRIES:       # forget the least used
                weakest = min(self.seen, key=lambda k: sum(self.seen[k].values()))
                self.seen.pop(weakest, None)
            self._dirty = True
        self.save()

    def top_phrases(self, limit=8):
        """The sentences this player's mishearings have turned into most often (used as a hint for the recogniser)."""
        totals = {}
        for options in self.seen.values():
            for sentence, count in options.items():
                totals[sentence] = totals.get(sentence, 0) + count
        return [s for s, _ in sorted(totals.items(), key=lambda kv: -kv[1])[:limit]]

    def count(self):
        return sum(1 for heard in self.seen if self.learned(heard))

    def save(self):
        if not self._dirty:
            return
        try:
            os.makedirs(os.path.dirname(str(self.path)) or ".", exist_ok=True)
            handle, temp = tempfile.mkstemp(dir=os.path.dirname(str(self.path)) or ".", suffix=".tmp")
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                json.dump({"_help": "How the speech recogniser mis-hears you. Safe to delete.", "heard": self.seen}, out, indent=1)
            os.replace(temp, self.path)
            self._dirty = False
        except Exception:
            log.warning("Could not save %s", self.path)

    def forget_all(self):
        with self._lock:
            self.seen.clear()
            self._dirty = True
        self.save()
