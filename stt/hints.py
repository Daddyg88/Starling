"""
The hint she gives the speech recogniser before it listens.

Whisper accepts a short piece of text and then spells words the way the hint spells them. A hint full of the words
she will hear (her name, Elite words, the phrases THIS player uses most) makes mishearings of those words much rarer,
which helps most for accents. It must stay short: Whisper only reads the end of a long hint.
"""

BASE = ("Commander. Elite Dangerous. galaxy map, system map, supercruise, hyperspace, fuel scoop, landing gear, "
        "cargo scoop, hardpoints, heat sink, shield cell, chaff, flight assist, silent running, night vision, "
        "neutron route, plot route, FSS, Void Compass, Felicity Farseer, Caspian Explorer.")
MAX_CHARS = 420
MAX_PHRASES = 12


def build_hint(wake_name="Starling", phrases=()):
    """'Starling. <the player's own most-used phrases>. <the Elite words>' - the name first, the words last."""
    parts = [(wake_name or "Starling").strip().rstrip(".") + "."]
    for phrase in list(phrases)[:MAX_PHRASES]:
        phrase = str(phrase).strip()
        if phrase and phrase not in parts:
            parts.append(phrase.rstrip(".") + ".")
    text = " ".join(parts)
    room = MAX_CHARS - len(text) - 1
    return (text + " " + BASE[:max(room, 0)]).strip() if room > 40 else text[:MAX_CHARS]
