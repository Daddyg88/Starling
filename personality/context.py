"""
FOLLOW-UPS THAT NEED THE LAST QUESTION - "and in Vienna?", "what about Spain?", "and 10?", "no, I meant Austria".

When a sentence is only a piece of a question, she rebuilds the whole question from the one before:
    "what is the capital of France"  +  "and Spain?"        ->  "what is the capital of spain"
    "what time is it in Melbourne"   +  "no I meant Vienna"  ->  "what time is it in vienna"
    "what is 5 times 3"              +  "and 10?"            ->  "what is 10 times 3"
Pure text work: no model, no network.
"""

import re

ELLIPSIS = re.compile(r"^(?:and |so |ok |okay |then )*(?:what about|how about|and what about|what of|and for|and in|and at|and)\s+"
                      r"(?:in |for |at |the )?(?P<x>[a-z0-9]+(?: [a-z0-9]+){0,3})$")
CORRECTION = re.compile(r"^(?:no |nope |sorry |not that |no no |oh |i mean |i said )*(?:i meant|i mean|i said|i was asking about|"
                        r"i was talking about|i asked about|i asked for|not that one|try)\s+(?:in |for |at |the )?(?P<x>[a-z0-9]+(?: [a-z0-9]+){0,5})$")
NOT_PIECES = {"you", "yourself", "me", "it", "that", "this", "them", "him", "her", "us", "now", "then", "else", "more", "so", "why", "how",
              "the other one", "the other", "other one", "other", "another", "another one", "one more", "the same", "that one", "this one"}
MARKERS = (" in ", " of ", " for ", " at ", " to ", " is ", " about ")


def piece_of(sentence, patterns=(ELLIPSIS, CORRECTION)):
    """The new piece ('spain') when the whole sentence is only a piece of a question, else None."""
    for pattern in patterns:
        found = pattern.match(sentence)
        if found:
            piece = found.group("x").strip()
            if piece and piece not in NOT_PIECES:
                return piece
    return None


def rewrite(previous, piece):
    """Put the new piece into the previous question, or None when that does not make sense."""
    previous, piece = (previous or "").strip(), (piece or "").strip()
    if not previous or not piece:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", piece):                      # "and 10?" swaps the first number
        if re.search(r"\d+(?:\.\d+)?", previous):
            return re.sub(r"\d+(?:\.\d+)?", piece, previous, count=1)
        return None
    padded = " " + previous + " "
    best = max((padded.rfind(m) for m in MARKERS), default=-1)
    if best < 0:
        return None
    marker = next(m for m in MARKERS if padded.rfind(m) == best)
    return (padded[:best] + marker + piece).strip()
