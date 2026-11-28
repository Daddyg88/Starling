"""Which of her lines does a tester hear again and again?

Reads the logs in a Starling diagnostics ZIP (or a plain starling.log), counts how often each line was said,
and lists the line pools that are small compared with how often they were used.

Run:   python tools/repeat_report.py path\\to\\starling-diagnostics.zip
Prints: uses, pool size (every wording she can pick for it), how many different lines were heard, and how often the
same line came again within her last 8 uses of that key. The worst pools are at the top: add lines there.
"""
import collections
import io
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SAID = re.compile(r"starling\.speech \| Said \[([^\]]*)\]: (.*)")


def read_logs(path):
    """All the text of every starling.log* inside a ZIP, or of one log file."""
    path = Path(path)
    if path.suffix.lower() == ".zip":
        out = []
        with zipfile.ZipFile(path) as z:
            for name in sorted(z.namelist(), reverse=True):             # .log.2 (oldest) first
                if "starling.log" in name.rsplit("/", 1)[-1]:
                    out.append(z.read(name).decode("utf-8", "replace"))
        return "\n".join(out)
    return path.read_text(encoding="utf-8", errors="replace")


def said_lines(text):
    """[(event key, what she said)] in the order she said them."""
    return [(m.group(1), m.group(2).strip()) for m in map(SAID.search, text.splitlines()) if m]


def build_report(rows, lines_by_key, window=8, min_uses=8):
    """lines_by_key: {key: [line text, ...]} (every key, mood variants included).
    Returns rows (score, uses, pool, distinct, close, key), worst first."""
    text_to_key = {}
    for key, texts in lines_by_key.items():
        for t in texts:
            t = t.strip()
            if t and (t not in text_to_key or len(key) < len(text_to_key[t])):
                text_to_key[t] = key

    def base(key):
        return key.split("_")[0] if key.split("_")[0] in lines_by_key else key

    uses = collections.defaultdict(list)
    for _event, said in rows:
        for part in [p.strip() for p in re.split(r"\s{3,}", said)] or [said]:
            key = text_to_key.get(part)
            if key:
                uses[base(key)].append(part)
    report = []
    for key, heard in uses.items():
        if len(heard) < min_uses:
            continue
        pool = sum(len(v) for k, v in lines_by_key.items() if k == key or k.startswith(key + "_"))
        close, last = 0, collections.deque(maxlen=window)
        for line in heard:
            close += line in last
            last.append(line)
        report.append((len(heard) / max(pool, 1), len(heard), pool, len(set(heard)), close, key))
    return sorted(report, reverse=True)


def load_pack_lines(pack="voicepacks/default"):
    from personality.dialogue import DialogueManager
    manager = DialogueManager(pack_dir=Path(__file__).resolve().parent.parent / pack).load()
    return {key: [line.text for line in lines if line.text] for key, lines in manager.lines.items()}


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    rows = said_lines(read_logs(argv[1]))
    report = build_report(rows, load_pack_lines())
    print("%d lines said. Worst pools first (uses per line in the pool; 'again' = same line within her last 8 uses)." % len(rows))
    print("%6s %5s %5s %6s %6s  %s" % ("ratio", "uses", "pool", "heard", "again", "key"))
    for ratio, uses, pool, distinct, close, key in report[:40]:
        print("%6.1f %5d %5d %6d %6d  %s" % (ratio, uses, pool, distinct, close, key))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
