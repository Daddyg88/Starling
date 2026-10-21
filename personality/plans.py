"""
"What are we doing today?"  Understanding the answer, and deciding which plan she is NOT in the mood for.

Each time she asks (once per login) she secretly picks ONE of the six activities that she does not fancy today.
    You choose that one  -> she grumbles but says she will go anyway, and you lose a mood point.
    You choose any other -> she is pleased, and you gain a mood point.
So at most one of the six choices is ever a bad point, and you do not know which until you choose it.

No microphone code here, so it is easy to test.
"""

import re

TOPICS = ("exploring", "mining", "combat", "trading", "exobiology", "antixeno")
SPOKEN = {"exploring": "exploring", "mining": "mining", "combat": "combat", "trading": "trading",
          "exobiology": "exobiology", "antixeno": "anti-xeno"}

_PATTERNS = {
    "antixeno": r"\b(anti ?-?x?eno\w*|x?eno\w*|zeno\w*|thargoids?|thargs?|hydras?|interceptors?|aliens?|bugs)\b",
    "exobiology": r"\b(exo ?-?bio\w*|bio\w*|organics?|samples?|sampling|genetics?|genetic samples?)\b",
    "mining": r"\b(min(?:e|es|ed|ing|er|ers)|prospect\w*|asteroids?|rocks?|refin\w*|laser mining|core mining)\b",
    "trading": r"\b(trad(?:e|es|ing|er)|haul\w*|cargo|deliver\w*|courier|commodit\w*|money|credits|profit|selling|buying)\b",
    "combat": r"\b(combat|fight\w*|bount(?:y|ies)|hunt\w*|shoot\w*|pirates?|battle\w*|kill\w*|conflict zones?|war|dogfights?)\b",
    "exploring": r"\b(explor\w*|discover\w*|scanning|honk\w*|deep space|road to riches|survey\w*|sightseeing|out there|neutron\w*)\b",
}
_COMPILED = {topic: re.compile(pattern) for topic, pattern in _PATTERNS.items()}
_PRIORITY = ("antixeno", "exobiology")          # these words beat "hunt" and "scan" when both are in one sentence
_NOTHING = re.compile(r"\b(nothing|not sure|dont know|do not know|no idea|no plans|whatever|surprise me|you choose|"
                      r"up to you|wing it|just (?:chill\w*|relax\w*|flying|cruising|vibing))\b")
MAX_WORDS = 16


def _clean(text):
    return " ".join(re.sub(r"[^a-z0-9' \-]", " ", (text or "").lower().replace("'", "")).replace("-", " ").split())


def topic_from(text):
    """'I think we shall go out exploring' -> 'exploring'.  'nothing really' -> 'none'.  Not an answer -> None."""
    cleaned = _clean(text)
    if not cleaned or len(cleaned.split()) > MAX_WORDS:
        return None
    for topic in _PRIORITY:
        if _COMPILED[topic].search(cleaned):
            return topic
    found = [(match.start(), topic) for topic, rx in _COMPILED.items() for match in [rx.search(cleaned)] if match]
    if found:
        return min(found)[1]
    if _NOTHING.search(cleaned):
        return "none"
    return None
