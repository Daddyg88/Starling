"""
FREE CHAT - she can simply talk with you, without any AI model.

Everything here is plain rules and word lists, so it is instant and tiny, and she stays honest: she never pretends to
know what she does not. When you say something that is not a command and not one of her known topics, she builds a
reply from up to three pieces, each picked from a pool of her own lines (voicepacks/default/freechat.json):

    1. a reaction that fits how you sound    ("That's rotten.", "Lovely.", "Mm, I see.")
    2. sometimes your own words turned round ("So you went to the shop.")
    3. a remark about the topic, and a question back, so the chat keeps going

Topics (food, work, family, pets, space, ships...) are found from the words you used (config/chat_topics.json).
After she asks you something you can just answer for a short while, without saying her name again; after a few
exchanges she closes the chat politely, so it never turns into an interrogation.

Safety first: if someone says they want to hurt themselves she drops the banter and answers with care
(Chat_Concern). And a garbled game command is never answered with chat: it is left for the normal "I didn't catch that".
"""
import json
import re

from core import paths
from core.logger import get_logger

log = get_logger("freechat")

CHAT_WINDOW_SECONDS = 25.0      # after she asks a question, you can answer without her name for this long
MAX_EXCHANGES = 4               # then she wraps the chat up politely
MIN_WORDS = 3
LONG_WORDS = 14
REFLECT_MAX_WORDS = 11

CRISIS = re.compile(r"\b(?:kill myself|killing myself|suicide|suicidal|end my life|end it all|want to die|wanna die|hurt myself|"
                    r"harm myself|self harm|cut myself|better off dead|no reason to live|dont want to be here anymore|"
                    r"dont want to live|take my own life|not worth living)\b")
SWEARS = {"fuck", "fucking", "fucked", "shit", "shitty", "bastard", "bitch", "cunt", "twat", "wanker", "bollocks", "piss", "pissed",
          "arse", "arsehole", "crap", "bloody", "damn", "dick", "prick"}
QUESTION_WORDS = {"what", "whats", "why", "how", "when", "where", "who", "whos", "which", "whose", "do", "does", "did", "is", "are",
                  "am", "was", "were", "can", "could", "would", "will", "should", "have", "has", "shall", "may", "isnt", "arent",
                  "dont", "wont", "whom"}
POSITIVE = {"good", "great", "happy", "love", "loved", "loving", "awesome", "amazing", "nice", "fun", "enjoy", "enjoyed", "won", "wow",
            "brilliant", "fantastic", "cool", "excellent", "perfect", "lovely", "best", "glad", "excited", "proud", "delighted",
            "wonderful", "beautiful", "fine", "cheerful", "pleased", "thrilled", "yay", "winning", "smashed", "nailed", "relaxed",
            "better", "promoted", "passed", "success", "celebrate", "celebrating"}
NEGATIVE = {"bad", "terrible", "awful", "hate", "hated", "sad", "angry", "annoyed", "tired", "boring", "bored", "sick", "ill", "hurts",
            "pain", "lost", "died", "failed", "worst", "rubbish", "horrible", "stressed", "worried", "upset", "lonely", "miserable",
            "exhausted", "broke", "sucks", "ruined", "depressed", "anxious", "nervous", "dreadful", "unhappy", "fed", "furious",
            "grim", "gutted", "rough", "worse", "crashed", "broken", "stuck", "struggling", "difficult", "hard", "lonely"}
NEGATORS = {"not", "no", "never", "dont", "cant", "isnt", "wasnt", "arent", "werent", "wont", "barely", "hardly", "didnt", "doesnt", "cannot"}
# command-like openings: a failed command must not get a chat reply
COMMAND_OPENERS = {"open", "close", "lower", "raise", "deploy", "retract", "turn", "switch", "plot", "set", "toggle", "show", "hide",
                   "launch", "dock", "jump", "engage", "enable", "disable", "activate", "deactivate", "fire", "target", "select", "boost",
                   "cancel", "clear", "request", "cycle", "next", "previous", "start", "stop", "press", "hold", "release", "drop", "pull",
                   "put", "bring", "take", "enter", "exit", "leave", "arm", "disarm", "scan", "honk", "reset", "zoom"}
_FLIP = {"i": "you", "im": "you are", "ive": "you have", "id": "you would", "ill": "you will", "my": "your", "me": "you", "mine": "yours",
         "myself": "yourself", "am": "are"}


def words_of(tidy):
    return re.findall(r"[a-z0-9]+", tidy)


def is_crisis(tidy):
    return bool(CRISIS.search(tidy))


def is_question(words):
    return bool(words) and words[0] in QUESTION_WORDS


def sentiment(words):
    """+1, 0 or -1 from a few dozen feeling words, with 'not good' turning round."""
    score = 0
    for index, word in enumerate(words):
        value = 1 if word in POSITIVE else (-1 if word in NEGATIVE else 0)
        if value and any(w in NEGATORS for w in words[max(0, index - 2):index]):
            value = -value
        score += value
    return 1 if score > 0 else (-1 if score < 0 else 0)


def flip(words):
    """'i went to my mums' -> 'you went to your mums'"""
    out = []
    for word in words:
        word = _FLIP.get(word, word)
        if word == "was" and out and out[-1] == "you":
            word = "were"
        out.append(word)
    return " ".join(out)


def can_reflect(words):
    if not (MIN_WORDS <= len(words) <= REFLECT_MAX_WORDS) or is_question(words):
        return False
    if any(w in SWEARS for w in words):
        return False
    return words[0] in ("i", "im", "ive", "my", "id", "ill")


def looks_like_command(words, vocabulary=()):
    """A garbled game command ('lower the lending gear') must not be answered with chat."""
    if not words:
        return True
    if words[0] in COMMAND_OPENERS:
        return True
    hits = sum(1 for w in words if len(w) >= 3 and w in vocabulary)
    return hits >= 2 and hits / len(words) >= 0.4          # mostly command words ("lower the lending gear"), not just a chatty sentence


class Topics:
    def __init__(self, topics):
        self.topics = {name: set(words) for name, words in topics.items()}

    def find(self, tidy):
        """The topic with the most matching words, or None."""
        padded = " %s " % tidy
        order = words_of(tidy)
        best, best_hits, best_first = None, 0, 0
        for name, keywords in self.topics.items():
            hits, first = 0, len(order) + 1
            for keyword in keywords:
                if " " in keyword:
                    at = padded.find(" %s " % keyword)
                    where = len(padded[:at].split()) if at >= 0 else -1
                else:
                    where = order.index(keyword) if keyword in order else (order.index(keyword + "s") if keyword + "s" in order else -1)
                if where >= 0:
                    hits += 1
                    first = min(first, where)
            # most matching words wins; on a tie, whichever was mentioned first
            if hits > best_hits or (hits == best_hits and hits and first < best_first):
                best, best_hits, best_first = name, hits, first
        return best


def load_topics(path=None):
    path = path or (paths.CONFIG_DIR / "chat_topics.json")
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
        return Topics(raw.get("topics", {}))
    except (OSError, ValueError):
        log.warning("No chat topics at %s: free chat has no topics", path)
        return Topics({})


# a few whole-sentence shapes she can use the thing you asked about
_DO_LIKE = re.compile(r"^(?:do you|have you|would you|did you|are you into) (?:ever )?(?:like|love|enjoy|eat|drink|play|watch|listen to|read|"
                      r"try|fancy|prefer|hate|dislike) (?P<x>.{2,40})$")
_FAV = re.compile(r"^(?:what is|whats|which is|what are) your (?:favou?rite|best|least favou?rite) (?P<x>.{2,30})$")
_EVER = re.compile(r"^have you (?:ever )?(?:been|seen|tried|visited|met|heard|eaten|played|watched|read|flown|gone)(?: to| in| at| on)? (?P<x>.{2,40})$")


def shape(tidy):
    """('Chat_DoLike', {'x': 'pizza'}) and friends for questions with a thing in them, else None."""
    for key, pattern in (("Chat_Ever", _EVER), ("Chat_DoLike", _DO_LIKE), ("Chat_Fav", _FAV)):
        found = pattern.match(tidy)
        if found:
            thing = flip(found.group("x").split())
            thing = re.sub(r"^(?:the |a |an |some |any )", "", thing)
            return key, {"x": thing}
    return None
