"""
Understanding a spoken yes or no, and "tell me a fact" requests. No microphone code here, so it is easy to test.

People answer in many ways ("yeah go on", "nah not now", "please do", "maybe later"), so this looks at words,
not exact sentences. A "no" word anywhere beats a "yes" word ("no thanks, maybe another time" is a no).
"""

import re

NO_WORDS = {"not", "never", "no", "nope", "nah", "nay", "negative", "later", "skip", "pass", "quiet", "silence", "dont", "shush", "hush"}
NO_PHRASES = (
    "no thanks", "no thank you", "not now", "not right now", "not really", "not today", "not interested", "maybe later",
    "another time", "some other time", "i'm good", "im good", "i am good", "i'm fine", "im fine", "leave it", "forget it",
    "shut up", "be quiet", "keep it to yourself", "i'm busy", "im busy", "not at the moment", "rather not", "hard pass",
    "no way", "absolutely not", "nope thanks", "nah thanks", "save it", "spare me", "later please", "ask me later",
)
YES_WORDS = {
    "yes", "yeah", "yep", "yup", "yea", "aye", "sure", "ok", "okay", "alright", "please", "definitely", "absolutely",
    "certainly", "affirmative", "roger", "indeed", "totally", "gladly", "happily", "obviously", "mhm", "yessir",
}
YES_PHRASES = (
    "go on", "go ahead", "tell me", "tell me more", "fire away", "why not", "of course", "sure thing", "sounds good",
    "i'd like that", "i would like that", "i'd love to", "i would love to", "let's do it", "lets do it", "let's go",
    "lets go", "go for it", "do it", "please do", "yes please", "i'm listening", "im listening", "hit me",
    "surprise me", "go on then", "i'm all ears", "im all ears", "sounds interesting", "that would be great", "bring it on",
    "why don't we", "why dont we", "sounds like a plan", "let's see", "lets see", "show me", "i'm in", "im in",
)

FACT_REQUEST = re.compile(
    r"\b(tell me|give me|got|have you got|share|say|hit me with)\b.*\b(fact|something interesting|something cool|trivia|a story)\b"
    r"|\bfun fact\b|\bdid you learn anything\b|\bwhat have you been reading\b|\banything interesting\b"
    r"|\bteach me something\b|\bsurprise me with\b.*\b(fact|something)\b",
    re.IGNORECASE)


def _clean(text):
    return re.sub(r"[^a-z0-9' \-]", " ", (text or "").lower()).replace("-", " ").strip()


def classify(text):
    """'yes', 'no' or None (not an answer)."""
    cleaned = " ".join(_clean(text).split())
    if not cleaned or len(cleaned.split()) > 7:
        return None                     # a long sentence is a command or a chat, not an answer
    padded = " %s " % cleaned
    if any(" %s " % p in padded for p in NO_PHRASES):
        return "no"
    if any(" %s " % p in padded for p in YES_PHRASES):
        return "yes"                    # "why not" is a yes even though it contains "not"
    words = set(cleaned.replace("'", "").split()) | set(cleaned.split())
    if words & NO_WORDS:
        return "no"
    if words & YES_WORDS:
        return "yes"
    return None


def wants_a_fact(text):
    return bool(FACT_REQUEST.search(text or ""))


A_WORDS = {"a", "ay", "eh", "alpha", "first", "1st", "one", "1", "top", "best", "either", "whichever"}
B_WORDS = {"b", "bee", "be", "bravo", "second", "2nd", "two", "2", "other", "last"}


def choose(text):
    """'A', 'B', 'no' or None for the A-or-B question about where to sell.
    "option b", "the second one", "bravo" -> B.  "yes" or "either" -> A (the better price).  "neither" or "no" -> 'no'."""
    cleaned = " ".join(_clean(text).split())
    if not cleaned or len(cleaned.split()) > 8:
        return None
    words = set(cleaned.replace("'", "").split()) | set(cleaned.split())
    if words & {"neither", "none", "cancel", "nevermind", "never"} or "never mind" in cleaned or "no thanks" in cleaned:
        return "no"
    if "one" in words and words & {"first", "1st", "second", "2nd", "last", "other", "top", "best"}:
        words.discard("one")                            # "the second one" means B, not A
    wants_a, wants_b = bool(words & A_WORDS), bool(words & B_WORDS)
    if wants_b and not wants_a:
        return "B"
    if wants_a and not wants_b:
        return "A"
    if wants_a and wants_b:
        return "A" if cleaned.find("a") <= cleaned.find("b") and "either" in words else None
    answer = classify(cleaned)
    if answer == "yes":
        return "A"
    return "no" if answer == "no" else None
