"""
THARGOID TITANS: "plot me a route to the nearest titan", "take me to Thor", "what happened to Cocijo".

The eight Titans are in config/titans.json. The plotting is done by RouteVoice (galaxy map up to 1000 light years, Spansh neutron route beyond).
On the way she tells the story of the Thargoid war, one piece per jump (voicepacks/default/titans.json), and on the jump into
the Titan's system she says when it was destroyed.
"""

import difflib
import json
import re

from core import paths
from core.logger import get_logger

log = get_logger("titans")

_GO = re.compile(r"\b(plot|set|take|bring|fly|get|navigate|head|go|route|course|lead|find|send)\b")
_STORY = re.compile(r"\b(tell|about|happened|story|history|destroyed|killed|died|fall|fell)\b")
_WHERE = re.compile(r"\bwhere\b")
_NEAREST = re.compile(r"\b(nearest|closest|near|nearby|next|local)\b")
FUZZY_CUTOFF = 0.8


class Titan:
    def __init__(self, data):
        self.name = str(data["name"])
        self.system = str(data["system"])
        self.body = str(data.get("body") or "")
        self.arrival = str(data.get("arrival") or "")
        self.order = int(data.get("order") or 0)
        self.destroyed = str(data.get("destroyed") or "")
        self.aliases = sorted({a.lower() for a in data.get("aliases", [])} | {self.name.lower()}, key=len, reverse=True)

    def fields(self):
        return {"titan": self.name, "system": self.system, "body": self.body, "arrival": self.arrival,
                "order": ORDINALS.get(self.order, str(self.order)), "destroyed": self.destroyed,
                "place": ("%s in %s" % (self.body, self.system)) if self.body else self.system}


ORDINALS = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh", 8: "eighth"}


def load(path=None):
    path = path or (paths.CONFIG_DIR / "titans.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        return [Titan(t) for t in raw.get("titans", [])]
    except (OSError, ValueError, KeyError, TypeError):
        log.exception("Could not read %s", path)
        return []


def find(titans, said):
    """The Titan named in the sentence, or None. Short names (Oya, Thor) must match exactly; longer ones may be a little misheard."""
    for titan in titans:
        for alias in titan.aliases:
            if re.search(r"\b%s\b" % re.escape(alias), said):
                return titan
    if "titan" in said:
        words = [w for w in said.split() if len(w) >= 5 and w not in ("titan", "titans", "thargoid", "nearest", "closest")]
        best, score = None, 0.0
        for titan in titans:
            if len(titan.name) < 5:
                continue
            for word in words:
                ratio = difflib.SequenceMatcher(None, word, titan.name.lower()).ratio()
                if ratio > score:
                    best, score = titan, ratio
        if score >= FUZZY_CUTOFF:
            return best
    return None


def parse(titans, said):
    """(titan or 'nearest', intent) with intent 'go', 'where' or 'story'; None when this was not about a Titan.
    `said` is lower case with the punctuation removed (navigation.voice.clean)."""
    mentions = bool(re.search(r"\btitans?\b", said))
    titan = find(titans, said)
    if titan is None and not mentions:
        return None
    if titan is None:
        who = "nearest"
        if not (_NEAREST.search(said) or _GO.search(said) or _WHERE.search(said)):
            return None
    else:
        who = titan
    if _STORY.search(said) and not _GO.search(said):
        return (who, "story") if who != "nearest" else None
    if _GO.search(said):
        return who, "go"
    if _WHERE.search(said):
        return who, "where"
    return None
