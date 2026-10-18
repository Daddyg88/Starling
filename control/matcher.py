"""
Turns what you SAID into a command, in plain everyday language.

How it works (simple version):
  1. Tidy the sentence: lower case, no "please / could you / the / my", and a few word swaps so
     "undercarriage", "wheels" and "landing gear" all become "gear".
  2. Every command in control/catalog.py was written as short templates such as
         "(lower|drop|deploy) gear"
     which are expanded into hundreds of exact sentences. If your sentence is one of them: done.
  3. Otherwise she compares it with all the sentences and takes the closest one, but only if it
     is very close, and NEVER if the two differ by an opposite word (up/down, open/close, next/previous...).
     That is how a slightly mis-heard word still works, but "raise the gear" can never be mistaken for "lower the gear".
"""

import difflib
import re
from dataclasses import dataclass
from typing import List, Optional

from control.catalog import CATALOG, MACROS

FUZZY_NORMAL = 0.84
LEARN_MIN_SCORE = 0.90        # only a near-certain match is remembered as "one of your phrases"
FUZZY_STRICT = 0.97          # commands that do something big (jump, supercruise)

# ---- tidying ----
_POLITE = [
    r"i would like you to", r"i d like you to", r"i want you to", r"i need you to", r"i would like to",
    r"i d like to", r"i want to", r"i need to", r"could you please", r"can you please", r"would you please",
    r"could you", r"can you", r"would you", r"will you", r"if you could", r"go ahead and", r"let s",
    r"lets", r"please", r"kindly", r"just", r"quickly", r"right now", r"for me", r"thanks", r"thank you",
    r"commander", r"cmdr", r"me", r"okay", r"ok", r"hey", r"now", r"actually", r"so", r"um", r"uh",
]
_POLITE_RE = re.compile(r"\b(?:%s)\b" % "|".join(_POLITE))
_ARTICLES = re.compile(r"\b(?:the|my|our|your|a|an|this|that|these|those|all|of)\b")

# word swaps: (pattern, replacement). Order matters.
SYNONYMS = [
    (r"\b(?:landing gear|landing gears|undercarriage|landing legs|landing legs|wheels?|gears?)\b", "gear"),
    (r"\b(?:galactic map|galaxy map|star map|stellar map|galmap|gal map|map of galaxy)\b", "galaxy map"),
    (r"\b(?:system map|solar system map|orrery|local map|sys map)\b", "system map"),
    (r"\b(?:hard points?|hardpoints?|weapons?|guns?|turrets?|lasers?)\b", "weapons"),
    (r"\b(?:cargo scoop|cargo hatch|cargo doors?|cargo bay doors?|cargo bay|scoop)\b", "scoop"),
    (r"\b(?:ship lights?|flood lights?|spot lights?|spotlights?|head lights?|headlights?|lights?)\b", "lights"),
    (r"\b(?:heat sinks?|heatsinks?|heat sync|heat sink)\b", "heatsink"),
    (r"\b(?:shield cell bank|shield cells?|shell cell|s c b|scb)\b", "shield cell"),
    (r"\b(?:chaff|flares?|countermeasures?|counter measures?)\b", "chaff"),
    (r"\b(?:frame shift drive|f s d|fsd)\b", "fsd"),
    (r"\b(?:super cruise|supercruise|super crews)\b", "supercruise"),
    (r"\b(?:hyper space|hyperspace|hyper drive|hyperdrive)\b", "hyperspace"),
    (r"\b(?:full spectrum scanner|full spectrum|f s s|fss)\b", "fss"),
    (r"\b(?:flight assistance|flight assist)\b", "flight assist"),
    (r"\b(?:silent running|silence|silent mode)\b", "silent running"),
    (r"\b(?:night vision|nightvision|night sight)\b", "night vision"),
    (r"\b(?:hostiles?|enem(?:y|ies)|bandits?|bad guys?|baddies|hostile ship|hostile target)\b", "hostile"),
    (r"\b(?:sub systems?|subsystems?)\b", "subsystem"),
    (r"\b(?:wing man|wingmen|wing mate|wingmate|wingman)\b", "wingman"),
    (r"\b(?:fire groups?|weapon groups?|firegroups?)\b", "fire group"),
    (r"\b(?:following|forward)\b", "next"),
    (r"\b(?:previous|prior|last|back)\b", "previous"),
    (r"\b(?:one hundred|a hundred|hundred)\b", "100"),
    (r"\b(?:seventy five|three quarters?|three quarter)\b", "75"),
    (r"\b(?:fifty|half)\b", "50"),
    (r"\bzero\b", "0"),
    (r"\bpercent\b", ""),
    (r"\b(?:one|won)\b", "1"),
    (r"\b(?:two|too)\b", "2"),
    (r"\bthree\b", "3"),
    (r"\bcomms?\b", "comms"),
]
_SYNONYMS = [(re.compile(p), r) for p, r in SYNONYMS]

# If the sentence and the closest template differ by one of these, they mean OPPOSITE things.
OPPOSITES = {"up", "down", "in", "out", "on", "off", "open", "close", "next", "previous", "raise", "lower",
             "deploy", "retract", "enable", "disable", "start", "stop", "left", "right", "increase",
             "decrease", "show", "hide", "enter", "exit", "leave", "arm", "disarm", "50", "75", "100", "0",
             "1", "2", "3", "analysis", "combat", "toggle"}


# Words that decide WHAT happens (raise / lower, open / close, on / off...). A mis-heard one of these is never guessed.
DIRECTION_WORDS = set(OPPOSITES)
for _name in ("OPEN_V", "CLOSE_V", "ON_V", "OFF_V", "DEPLOY_V", "RETRACT_V"):
    for _option in MACROS[_name].strip("()").split("|"):
        DIRECTION_WORDS.update(_option.split())


def normalise(text):
    """'Could you please lower the landing gear?' -> 'lower gear'"""
    text = (text or "").lower().replace("&", " and ")
    text = re.sub(r"['’]", " ", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = " " + re.sub(r"\s+", " ", text).strip() + " "
    text = _POLITE_RE.sub(" ", text)
    text = _ARTICLES.sub(" ", text)
    for pattern, replacement in _SYNONYMS:
        text = pattern.sub(replacement, text)
    text = re.sub(r"\s+", " ", text).strip()
    # "turn the lights on" -> "turn on lights"
    text = re.sub(r"^(turn|switch|put) (.+?) (on|off)$", r"\1 \3 \2", text)
    return text


def expand(spec):
    """'(open|show) [the] map' -> ['open the map', 'open map', 'show the map', 'show map']"""
    for name, value in MACROS.items():
        spec = spec.replace("{%s}" % name, value)
    return [" ".join(sentence.split()) for sentence in _expand_groups(spec)]


def _expand_groups(spec):
    found = re.search(r"\(([^()]*)\)|\[([^\[\]]*)\]", spec)
    if not found:
        return [spec]
    options = found.group(1).split("|") if found.group(1) is not None else found.group(2).split("|") + [""]
    out = []
    for option in options:
        out += _expand_groups(spec[:found.start()] + option + spec[found.end():])
    return out


@dataclass
class Match:
    command: object
    intent: str            # "on", "off", "toggle" or "press"
    phrase: str            # the template sentence it matched
    score: float           # 1.0 = exact


class Matcher:
    def __init__(self, commands=None, learning=None):
        self.learning = learning                 # control/learning.py: remembers how you get mis-heard
        self.commands = list(CATALOG if commands is None else commands)
        self.index = {}                      # sentence -> (command, intent)
        self.conflicts = []                  # sentences claimed by two different commands (a bug; tests check)
        for command in self.commands:
            self._index(command)
        self._sentences = list(self.index)

    def _index(self, command):
        for intent, specs in command.phrases.items():
            for spec in specs:
                for sentence in expand(spec):
                    clean = normalise(sentence)
                    if not clean:
                        continue
                    owner = self.index.get(clean)
                    if owner is None:
                        self.index[clean] = (command, intent)
                    elif owner[0].id != command.id or owner[1] != intent:
                        self.conflicts.append((clean, owner[0].id, command.id))

    def add(self, command):
        """Teach the matcher one more command while she is running (used for new Void Compass overlays)."""
        if any(c.id == command.id for c in self.commands):
            return False
        self.commands.append(command)
        self._index(command)
        self._sentences = list(self.index)
        return True

    def match(self, text):
        clean = normalise(text)
        if not clean:
            return None
        hit = self.index.get(clean)
        if hit:
            return Match(hit[0], hit[1], clean, 1.0)
        if self.learning is not None:
            known = self.learning.learned(clean)          # one of YOUR phrases she has learned
            if known in self.index:
                return Match(self.index[known][0], self.index[known][1], known, 1.0)
        found = self._fuzzy(clean)
        if (found is not None and self.learning is not None and not found.command.strict
                and found.score >= LEARN_MIN_SCORE):
            self.learning.note(clean, found.phrase)
        return found

    def _fuzzy(self, clean):
        words = set(clean.split())
        if len(clean) < 4:
            return None
        sm = difflib.SequenceMatcher()
        sm.set_seq2(clean)
        best = None
        for sentence in self._sentences:
            sm.set_seq1(sentence)
            if sm.real_quick_ratio() < FUZZY_NORMAL or sm.quick_ratio() < FUZZY_NORMAL:
                continue
            score = sm.ratio()
            if best is not None and score <= best[0]:
                continue
            if score < FUZZY_NORMAL:
                continue
            different = words ^ set(sentence.split())
            if different & DIRECTION_WORDS:
                continue
            best = (score, sentence)
        if best is None:
            return None
        command, intent = self.index[best[1]]
        if command.strict and best[0] < FUZZY_STRICT:
            return None
        return Match(command, intent, best[1], best[0])

    def split(self, text):
        """'lower the gear and open the galaxy map' -> [Match, Match] (all parts must be understood)."""
        pieces = [p for p in re.split(r"\b(?:and then|and also|and|then|also|after that)\b|,", (text or "").lower()) if p.strip()]
        if len(pieces) < 2 or len(pieces) > 3:
            return []
        matches = [self.match(p) for p in pieces]
        return matches if all(matches) else []

    def phrase_count(self):
        return len(self.index)
