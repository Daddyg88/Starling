"""
MEANING MATCHING - she understands a question even when you word it in a way nobody wrote a pattern for.

The brain's patterns (config/brain_intents.json) are exact: "do you like me" works, "are you fond of me at all" does not.
This is the second chance she gets when no pattern fits. config/brain_examples.json lists several example sentences for
each chatty topic. Your sentence and every example are boiled down to their important words (plurals, tenses and
spelling variants folded together, "love / enjoy / adore" counted as one), weighted so that rare words count more than
common ones, and compared. She only answers when ONE topic is clearly the best match; if two topics are close, or
nothing is close, she says nothing and the normal "I didn't catch that" happens. A wrong answer is worse than none.

It is plain arithmetic on a few hundred words: instant and tiny. It only ever picks the chatty "line" topics (opinions,
feelings, jokes, stories), never anything that touches the game or presses a key.
"""
import json
import math
import re

from core import paths
from core.logger import get_logger

log = get_logger("meaning")

MIN_SCORE = 0.70        # how close the best example must be (1.0 = same words)
MIN_MARGIN = 0.12       # and how far ahead of the best example of any OTHER topic
MIN_WORDS = 2           # a single word is too little to go on
NOTHING = "_Nothing"     # the decoys: sentences that are close to a topic but must get no answer
MIN_KNOWN = 0.6         # and at least this share of the important words must be ones the examples use at all

STOP = {"a", "an", "the", "is", "are", "am", "was", "were", "be", "been", "do", "does", "did", "to", "of", "it", "its", "that",
        "this", "these", "those", "please", "hey", "hi", "starling", "just", "so", "really", "very", "quite", "kind", "sort",
        "actually", "ever", "even", "at", "all", "bit", "little", "then", "well", "ok", "okay", "oh", "um", "uh", "like_to",
        "tell", "say", "ask", "give", "can", "could", "would", "will", "shall", "should", "might", "may", "need", "want"}
# words that mean (nearly) the same thing, folded to one
SYNONYMS = {
    "favorite": "fave", "favourite": "fave", "fav": "fave", "best": "fave", "preferred": "fave",
    "love": "like", "enjoy": "like", "adore": "like", "fancy": "like", "fond": "like", "into": "like", "prefer": "like",
    "hate": "dislike", "despise": "dislike", "loathe": "dislike",
    "afraid": "scared", "frightened": "scared", "terrified": "scared", "nervous": "scared", "worried": "scared", "anxious": "scared",
    "fear": "scared", "frighten": "scared",
    "sad": "unhappy", "down": "unhappy", "miserable": "unhappy", "depressed": "unhappy", "gloomy": "unhappy", "blue": "unhappy",
    "glad": "happy", "cheerful": "happy", "delighted": "happy", "thrilled": "happy", "excited": "happy", "joyful": "happy",
    "mad": "angry", "furious": "angry", "annoyed": "angry", "cross": "angry", "irritated": "angry", "livid": "angry",
    "exhausted": "tired", "sleepy": "tired", "knackered": "tired", "drained": "tired", "shattered": "tired", "weary": "tired",
    "starving": "hungry", "peckish": "hungry", "famished": "hungry",
    "lonely": "lonely", "alone": "lonely", "isolated": "lonely",
    "stupid": "dumb", "idiot": "dumb", "useless": "dumb", "thick": "dumb", "rubbish": "dumb", "dim": "dumb",
    "clever": "smart", "brainy": "smart", "intelligent": "smart", "brilliant": "smart", "genius": "smart", "bright": "smart",
    "hilarious": "funny", "amusing": "funny", "joke": "joke", "jokes": "joke", "gag": "joke", "pun": "joke", "puns": "joke", "humour": "joke", "humor": "joke",
    "boring": "bored", "dull": "bored", "tedious": "bored",
    "old": "age", "years": "age", "birthday": "age",
    "rest": "sleep", "nap": "sleep", "slumber": "sleep", "snooze": "sleep", "bed": "sleep",
    "dreams": "dream", "dreaming": "dream", "nightmare": "dream",
    "emotion": "feeling", "emotions": "feeling", "feelings": "feeling", "feel": "feeling",
    "girl": "gender", "boy": "gender", "male": "gender", "female": "gender", "woman": "gender", "man": "gender", "lady": "gender",
    "colour": "colour", "color": "colour", "hue": "colour", "shade": "colour",
    "meal": "food", "snack": "food", "dinner": "food", "lunch": "food", "breakfast": "food", "eat": "food", "dish": "food",
    "tune": "music", "song": "music", "band": "music", "singer": "music", "album": "music", "artist": "music", "songs": "music",
    "planet": "place", "star": "place", "system": "place", "station": "place", "moon": "place", "location": "place",
    "poem": "poem", "verse": "poem", "rhyme": "poem", "poetry": "poem", "sonnet": "poem", "limerick": "poem",
    "tale": "story", "stories": "story", "bedtime": "story", "yarn": "story",
    "advice": "quote", "wisdom": "quote", "quotes": "quote", "proverb": "quote", "saying": "quote",
    "future": "fortune", "destiny": "fortune", "horoscope": "fortune", "predict": "fortune", "prediction": "fortune", "fate": "fortune",
    "insult": "roast", "burn": "roast", "mock": "roast", "tease": "roast", "slate": "roast",
    "praise": "compliment", "flatter": "compliment", "flattery": "compliment", "nice": "compliment",
    "life": "meaning", "purpose": "meaning", "existence": "meaning", "universe": "meaning",
    "hobby": "hobby", "hobbies": "hobby", "pastime": "hobby", "spare": "hobby", "fun": "hobby", "free": "hobby",
    "secret": "secret", "confession": "secret", "confess": "secret",
    "stream": "stream", "viewers": "viewer", "audience": "viewer", "watchers": "viewer", "chat": "viewer", "followers": "viewer",
    "hello": "greet", "welcome": "greet", "greet": "greet", "introduce": "greet",
    "bye": "farewell", "goodbye": "farewell", "goodnight": "farewell", "later": "farewell",
    "win": "win", "won": "win", "victory": "win", "succeeded": "win", "nailed": "win", "triumph": "win",
    "oops": "oops", "whoops": "oops", "blunder": "oops", "mistake": "oops", "messed": "oops", "screwed": "oops",
    "close": "close", "narrow": "close", "escape": "close", "escaped": "close", "phew": "close",
    "fight": "combat", "fighting": "combat", "battle": "combat", "shooting": "combat", "killing": "combat", "pvp": "combat",
    "explore": "exploring", "exploration": "exploring", "exploring": "exploring", "discover": "exploring", "discovering": "exploring",
    "trade": "trading", "trading": "trading", "hauling": "trading", "mining": "trading", "cargo": "trading", "money": "trading",
    "thargoid": "thargoid", "thargoids": "thargoid", "alien": "thargoid", "aliens": "thargoid", "bug": "thargoid", "bugs": "thargoid",
    "guardian": "guardian", "guardians": "guardian", "ruins": "guardian", "ancient": "guardian",
    "carrier": "carrier", "carriers": "carrier",
    "human": "humanity", "humans": "humanity", "people": "humanity", "mankind": "humanity", "humanity": "humanity",
    "wish": "wants", "desire": "wants", "dream_of": "wants", "hope": "wants",
    "rain": "weather", "sunny": "weather", "forecast": "weather", "temperature": "weather", "cloudy": "weather",
    "name": "nickname", "nickname": "nickname", "callsign": "nickname",
    "cheer": "cheer", "comfort": "cheer", "motivate": "cheer", "encourage": "cheer", "perk": "cheer", "pep": "cheer",
    "abilities": "ability", "skills": "ability", "capable": "ability", "capabilities": "ability", "features": "ability",
    "news": "new", "updates": "new", "update": "new", "changed": "new", "latest": "new",
    "choose": "pick", "pick": "pick", "decide": "pick", "toss": "pick",
    "rather": "rather", "prefer_to": "rather",
    "chat_up": "pickup", "flirt": "pickup", "chatup": "pickup", "pickup": "pickup",
}


CONTRACTIONS = {"im": "i", "ive": "i", "ill": "i", "youre": "you", "youve": "you", "youll": "you", "whats": "what", "hows": "how",
                "thats": "that", "theres": "there", "cant": "cannot", "wont": "will", "dont": "not", "doesnt": "not", "didnt": "not",
                "isnt": "not", "arent": "not", "wasnt": "not", "gonna": "going", "wanna": "want", "gotta": "must", "cuz": "because"}


def stem(word):
    """A crude fold of plurals and tenses: 'sleeping' and 'sleeps' both become 'sleep'."""
    for tail, cut in (("ing", 3), ("ed", 2), ("es", 2), ("s", 1)):
        if word.endswith(tail) and len(word) - cut >= 3 and not word.endswith("ss"):
            return word[:-cut]
    return word


def tokens(text):
    out = []
    for word in re.findall(r"[a-z0-9]+", (text or "").lower().replace("'", "")):
        word = CONTRACTIONS.get(word, word)
        if word in STOP:
            continue
        stemmed = stem(word)
        for candidate in (word, stemmed, stemmed + "e"):          # 'loving' -> 'lov' -> 'love' -> 'like'
            if candidate in SYNONYMS:
                word = stem(SYNONYMS[candidate])       # the folded word is stemmed too, so 'tired' and 'exhausted' meet
                break
        else:
            word = stemmed
        if word:
            out.append(word)
    return out


class Meaning:
    def __init__(self, examples):
        """examples: {intent key: [example sentences]}"""
        self.entries = []                       # (key, {word: weight}, length)
        documents = [(key, tokens(text)) for key, texts in examples.items() for text in texts]
        documents = [(key, words) for key, words in documents if words]
        count = len(documents) or 1
        containing = {}
        for _key, words in documents:
            for word in set(words):
                containing[word] = containing.get(word, 0) + 1
        self.idf = {word: math.log((count + 1) / (n + 0.5)) + 0.3 for word, n in containing.items()}
        for key, words in documents:
            self.entries.append((key, self._vector(words)))

    def _vector(self, words):
        vector = {}
        for word in words:
            vector[word] = vector.get(word, 0.0) + self.idf.get(word, 1.6)      # a word no example has is rare, so it weighs a lot
        norm = math.sqrt(sum(v * v for v in vector.values())) or 1.0
        return {word: v / norm for word, v in vector.items()}

    def best(self, text):
        """(intent key, score) of the one clearly best topic for this sentence, or None."""
        words = tokens(text)
        if len(words) < MIN_WORDS:
            return None
        known = [w for w in words if w in self.idf]
        if not known or len(known) / len(words) < MIN_KNOWN:
            return None
        vector = self._vector(words)
        scores = {}
        for key, entry in self.entries:
            score = sum(weight * entry.get(word, 0.0) for word, weight in vector.items())
            if score > scores.get(key, 0.0):
                scores[key] = score
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        if not ranked or ranked[0][1] < MIN_SCORE:
            return None
        if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < MIN_MARGIN:
            return None
        if ranked[0][0] == NOTHING:
            return None
        return ranked[0]


def load_meaning(path=None):
    path = path or (paths.CONFIG_DIR / "brain_examples.json")
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        log.warning("No brain examples at %s: meaning matching is off", path)
        return None
    examples = {k: v for k, v in raw.items() if not k.startswith("_") and isinstance(v, list)}
    if isinstance(raw.get("_decoys"), list):
        examples[NOTHING] = raw["_decoys"]
    return Meaning(examples) if examples else None
