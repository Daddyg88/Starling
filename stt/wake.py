"""
Decides whether you said her name, and what came after it.

Speech recognition does not always spell "Starling" the same way ("Tet co", "Tedko", "Hey Starling!"),
so the first word or two are compared loosely to her name.
"""

import difflib
import re

_FILLER = {"hey", "hi", "ok", "okay", "yo", "oi", "hello"}


def _words(text):
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def _close(candidate, wake):
    if not candidate:
        return False
    return difflib.SequenceMatcher(None, candidate, wake).ratio() >= 0.72


def parse_wake(text, wake_phrase="Starling"):
    """
    Returns (heard_her_name, the_rest_of_what_you_said).
        "Hey Starling, open the galaxy map" -> (True, "open the galaxy map")
        "open the galaxy map"            -> (False, "open the galaxy map")
    """
    wake = "".join(_words(wake_phrase)) or "starling"
    words = _words(text)
    start = 0
    while start < len(words) and words[start] in _FILLER and start < 2:
        start += 1
    for take in (1, 2):                         # "starling" or "star ling"
        candidate = "".join(words[start:start + take])
        if len(words) >= start + take and _close(candidate, wake):
            return True, " ".join(words[start + take:])
    return False, " ".join(words)
