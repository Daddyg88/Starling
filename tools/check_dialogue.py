"""Looks through all of her lines for mistakes that are easy to miss by eye.

Run it from the project folder:   python tools/check_dialogue.py
It prints what it found and exits with 1 if there is anything serious. tests/test_content_check.py runs it too.

Serious:  broken {braces}, a line used twice for the same key, a tester's name outside eoc.json, an empty line.
Notes:    very long lines (they are cut into sentences when spoken), the same line under two different keys."""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMES = ("curd nerd", "curdnerd")       # real people (testers): never named in what she says; the player's own name comes from the journals
ALLOWED_NAMES = {"eoc.json"}
LONG = 400
FIELD = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def texts_of(value):
    for item in value if isinstance(value, list) else []:
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            yield item["text"]


def check(folder=None):
    """Returns (serious, notes): two lists of plain sentences."""
    folder = Path(folder) if folder else ROOT / "voicepacks" / "default"
    serious, notes = [], []
    seen_under = defaultdict(set)
    for file in sorted(folder.glob("*.json")):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except ValueError as error:
            serious.append("%s is not valid JSON: %s" % (file.name, error))
            continue
        for key, value in data.items():
            if not isinstance(value, list):
                continue
            used = set()
            for text in texts_of(value):
                where = "%s / %s" % (file.name, key)
                if not text.strip():
                    serious.append("%s has an empty line" % where)
                    continue
                if text in used:
                    serious.append("%s says %r twice" % (where, text[:60]))
                used.add(text)
                inner = re.findall(r"\{([^{}]*)\}", text)
                if text.count("{") != text.count("}") or text.count("{") != len(inner) or not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(:[^{}]*)?", x) for x in inner):
                    serious.append("%s has broken braces: %r" % (where, text[:60]))
                lowered = text.lower()
                if file.name not in ALLOWED_NAMES and any(name in lowered for name in NAMES):
                    serious.append("%s names a real person: %r" % (where, text[:60]))
                if len(text) > LONG:
                    notes.append("%s has a very long line (%d characters)" % (where, len(text)))
                seen_under[text].add(key)
    for text, keys in seen_under.items():
        if len(keys) > 1 and len(text) > 25:
            notes.append("the same line is under %d keys (%s): %r" % (len(keys), ", ".join(sorted(keys)[:3]), text[:50]))
    return serious, notes


def main():
    serious, notes = check()
    for line in serious:
        print("PROBLEM:", line)
    for line in notes[:40]:
        print("note:   ", line)
    if len(notes) > 40:
        print("note:    ... and %d more notes" % (len(notes) - 40))
    print("%d problems, %d notes" % (len(serious), len(notes)))
    return 1 if serious else 0


if __name__ == "__main__":
    sys.exit(main())
