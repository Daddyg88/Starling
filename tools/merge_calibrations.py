"""Merge the settlement line-ups players worked out into the file that ships with Starling.

HOW (the maintainer, in the Starling folder):
    python tools/merge_calibrations.py  diagnostics1.zip  diagnostics2.zip  some_settlement_calibration.json
Each argument is a diagnostics zip (the settlement_calibration.json inside it is used) or a settlement_calibration.json file.
It prints what it added, skipped and what CONFLICTS, and rewrites maps/known_calibrations.json. Add --dry-run to only print.
Then run the tests, bump the version and push as usual.
"""
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from navigation import settlement_share          # noqa: E402
from navigation.settlement_maps import SettlementMaps          # noqa: E402

TARGET = ROOT / "maps" / "known_calibrations.json"
NOTE = ("Lined-up maps shipped with the app (MarketID -> line-up), worked out by players walking the settlement. "
        "Same format as data/settlement_calibration.json. Add more with tools/merge_calibrations.py (never by hand).")


def read_source(path):
    """The MarketID -> entry dictionary in a zip or json file, or {} with a reason printed."""
    path = Path(path)
    try:
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as bundle:
                names = [n for n in bundle.namelist() if n.endswith("settlement_calibration.json")]
                if not names:
                    print("%s: no settlement_calibration.json inside (nothing was lined up on that machine, or it is an old zip)" % path.name)
                    return {}
                data = json.loads(bundle.read(names[0]).decode("utf-8"))
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print("%s: could not read (%s)" % (path.name, error))
        return {}
    return data if isinstance(data, dict) else {}


def main(argv):
    dry = "--dry-run" in argv
    sources = [a for a in argv if not a.startswith("--")]
    if not sources:
        print(__doc__)
        return 1
    try:
        shipped = json.loads(TARGET.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        shipped = {}
    map_ids = set(SettlementMaps().maps)
    merged = {k: v for k, v in shipped.items() if not k.startswith("_")}
    for source in sources:
        merged, report = settlement_share.merge(merged, read_source(source), map_ids)
        print("== %s" % Path(source).name)
        for line in report or ["nothing in it"]:
            print("  " + line)
    if dry:
        print("(dry run: nothing written)")
        return 0
    out = {"_note": NOTE}
    out.update(dict(sorted(merged.items())))
    TARGET.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print("wrote %s (%d settlements)" % (TARGET.relative_to(ROOT), len(merged)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
