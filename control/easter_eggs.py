"""Private phrases. They are NOT in the command catalog, so they never appear in the help, the dashboard lists or the website.

rewrite(text) turns a secret phrase into an ordinary command sentence (or returns None), and the normal command runner then
does the real work, with all its usual safety checks."""

import re

_SHOW_EM = re.compile(r"\bshow\s+(?:em|them|him|her|the\s+(?:lads|boys|lot))\s+(?:your|ur|you)\s+(?:tits|titties|boobs)\b")


def rewrite(text):
    said = re.sub(r"[^a-z ]", " ", str(text or "").lower().replace("'", ""))
    said = re.sub(r"\s+", " ", said).strip()
    if _SHOW_EM.search(said):
        return "deploy hardpoints"
    return None
