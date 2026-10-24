"""
THE ENGINEERS: who they are, where they live, and how to say their names.

config/engineers.json holds all 38 (name, system, station, and the system's galaxy coordinates).
You can say a first name, a last name, a nickname or the full name: "Felicity", "Farseer", "Felicity Farseer",
"Dekker", "the Dweller", "Sarge", "Tod McQuinn". Titles (Colonel, Professor, The) are optional.
A word that only fits one engineer is enough; if the microphone mishears a name she picks the closest one (above 80 percent alike).
"""

import difflib
import json
import math
import re

from core import paths
from core.logger import get_logger

log = get_logger("engineers")

SKIP_WORDS = {"the", "colonel", "professor", "of", "and"}
FUZZY_CUTOFF = 0.82
MIN_FUZZY_LENGTH = 4


class Engineer:
    def __init__(self, data):
        self.name = str(data["name"])
        self.system = str(data["system"])
        self.station = str(data.get("station") or "")
        self.pos = (float(data["x"]), float(data["y"]), float(data["z"]))
        self.extra = [str(a).lower() for a in data.get("aliases", [])]

    def spoken(self):
        """The name as it should be said: Tod 'The Blaster' McQuinn -> Tod The Blaster McQuinn."""
        return re.sub(r"['\"]", "", self.name)

    def words(self):
        text = re.sub(r"[^a-z0-9 ]", " ", self.name.lower())
        return [w for w in text.split() if w]

    def aliases(self):
        """Every way of saying this engineer's name, longest first."""
        words = self.words()
        found = {" ".join(words)}
        useful = [w for w in words if w not in SKIP_WORDS]
        found.add(" ".join(useful))
        for word in useful:
            if len(word) >= 3:
                found.add(word)
        if len(useful) >= 2:
            found.add(useful[0] + " " + useful[-1])
        if words and words[0] == "the" and len(words) > 1:
            found.add(" ".join(words[1:]))
        found.update(self.extra)
        return sorted((a for a in found if a), key=len, reverse=True)


def load(path=None):
    path = path or (paths.CONFIG_DIR / "engineers.json")
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        log.exception("Could not read %s", path)
        return []
    found = []
    for item in raw.get("engineers", []):
        try:
            found.append(Engineer(item))
        except (KeyError, TypeError, ValueError):
            log.warning("Skipped a broken engineer entry: %s", item)
    return found


class EngineerBook:
    def __init__(self, engineers=None):
        self.engineers = engineers if engineers is not None else load()
        self._table = {}
        for engineer in self.engineers:
            for alias in engineer.aliases():
                self._table.setdefault(alias, []).append(engineer)

    def find(self, text):
        """The engineer meant by this spoken text, or None (also None when the word fits two engineers)."""
        said = re.sub(r"[^a-z0-9 ]", " ", str(text or "").lower())
        said = " ".join(w for w in said.split() if w not in ("engineer", "engineers", "cmdr", "commander", "base", "mr", "miss", "mrs"))
        if said.startswith("the engineer "):
            said = said[13:]
        if not said:
            return None
        hit = self._table.get(said)
        if hit:
            return hit[0] if len(hit) == 1 else None
        if len(said) < MIN_FUZZY_LENGTH:
            return None
        close = difflib.get_close_matches(said, list(self._table), n=1, cutoff=FUZZY_CUTOFF)
        if close and len(self._table[close[0]]) == 1:
            return self._table[close[0]][0]
        return None


def distance(a, b):
    """Light years between two (x, y, z) points, or None if either is unknown."""
    if not a or not b:
        return None
    return math.dist(a, b)
