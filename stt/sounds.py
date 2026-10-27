"""
SOUND-ALIKE matching: words that sound the same to a listener, even when an accent changes how they are said.

Speech recognition writes down what it THINKS it heard. With a German, French, Spanish or strong regional accent that
is often a different real word: "plot" becomes "blot", "three" becomes "tree", "Starling" becomes "Sterling" or
"Shtarling". sound_key() boils a word down to a rough "how it sounds" code so such words get the SAME code:

    plot, blot            -> the same code      (b and p are folded: many accents blur them)
    three, tree, free     -> close codes        (th, t, d are folded)
    Starling, Sterling    -> the same code      (the vowels are folded)

It is deliberately loose. It is only ever used to REPAIR a word that is not a word she knows, and only when exactly
one word she knows has that code (control/matcher.py), so it cannot turn one command into the opposite one.
"""

import re

_RULES = [
    (r"^kn", "n"), (r"^wr", "r"), (r"^wh", "v"), (r"ph", "f"), (r"sch", "s"), (r"tch", "s"), (r"sh", "s"),
    (r"ch", "s"), (r"th", "t"), (r"ck", "k"), (r"qu", "kv"), (r"x", "ks"), (r"c(?=[eiy])", "s"), (r"c", "k"),
    (r"q", "k"), (r"z", "s"), (r"w", "v"), (r"b", "p"), (r"d", "t"), (r"g", "k"), (r"h", ""),
]
_RULES = [(re.compile(pattern), replacement) for pattern, replacement in _RULES]


def sound_key(word):
    """A rough 'how it sounds' code for one word. Numbers are returned unchanged."""
    word = re.sub(r"[^a-z0-9]", "", (word or "").lower())
    if not word or word.isdigit():
        return word
    for pattern, replacement in _RULES:
        word = pattern.sub(replacement, word)
    word = re.sub(r"[aeiouy]+", "a", word)               # which vowel is the one thing accents change most
    word = re.sub(r"(.)\1+", r"\1", word)                # double letters
    word = re.sub(r"(?<=a)r(?!a)", "", word)             # "starling" and "stalling" sound alike without the r
    if len(word) > 2 and word.endswith("a"):
        word = word[:-1]                                 # a silent final vowel
    return word


def same_sound(first, second):
    key = sound_key(first)
    return bool(key) and key == sound_key(second)
