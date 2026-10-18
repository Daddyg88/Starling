"""
The book of facts. She never repeats one until she has told you all of them (the list of used ones is saved in
data/facts_seen.json, so it survives updates and restarts).
"""

import hashlib
import json
import random

from core import paths
from core.logger import get_logger

log = get_logger("facts")

TOPICS = {
    "all": ("Fact_Elite", "Fact_Real", "Fact_Planets"),
    "elite": ("Fact_Elite",),
    "real": ("Fact_Real",),
    "planets": ("Fact_Planets",),
}


def _id(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


class FactBook:
    def __init__(self, dialogue, save_path=None, rng=None, persist=True):
        self.dialogue = dialogue
        self.save_path = save_path or (paths.DATA_DIR / "facts_seen.json")
        self.rng = rng or random.Random()
        self.persist = persist
        self.seen = set()
        self._load()

    def _load(self):
        if not self.persist:
            return
        try:
            with open(self.save_path, "r", encoding="utf-8") as handle:
                self.seen = set(json.load(handle).get("seen", []))
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, AttributeError):
            log.warning("Could not read the list of facts already told; starting again")

    def _save(self):
        if not self.persist:
            return
        try:
            self.save_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.save_path.with_suffix(".tmp")
            with open(temp, "w", encoding="utf-8") as handle:
                json.dump({"seen": sorted(self.seen)}, handle)
            temp.replace(self.save_path)
        except OSError:
            log.warning("Could not save the facts already told", exc_info=True)

    def _all(self, topic):
        lines = []
        for key in TOPICS.get(topic, TOPICS["all"]):
            lines += [line.text for line in self.dialogue.lines.get(key, [])]
        return lines

    def count(self, topic="all"):
        return len(self._all(topic))

    def next(self, topic="all"):
        """A fact she has not told you yet (or None if the pack has none)."""
        everything = self._all(topic)
        if not everything:
            return None
        fresh = [t for t in everything if _id(t) not in self.seen]
        if not fresh:                                    # told them all: start the book again
            self.seen -= {_id(t) for t in everything}
            fresh = everything
        choice = self.rng.choice(fresh)
        self.seen.add(_id(choice))
        self._save()
        return choice
