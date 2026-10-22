"""
Her seven moods, from best to worst, and which older mood each new one falls back on.

    Infatuated  (new, above Close)      Close  Friendly  Neutral  Sarcastic  Frustrated      Upset  (new, below Frustrated)

A line written for Close is also used when she is Infatuated, and a line written for Frustrated is also used when she is
Upset, so every line she already has works in the new moods. voicepacks/default/moods.json adds lines of their own.
"""

ORDER = ("Upset", "Frustrated", "Sarcastic", "Neutral", "Friendly", "Close", "Infatuated")
PARENT = {"Infatuated": "Close", "Upset": "Frustrated"}
GOOD = ("Friendly", "Close", "Infatuated")
BAD = ("Sarcastic", "Frustrated", "Upset")


def base(mood):
    """The older mood a new one is built on (Infatuated -> Close, Upset -> Frustrated); other moods are unchanged."""
    return PARENT.get(mood, mood)
