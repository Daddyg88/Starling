"""Make Starling's neutron star list from a Spansh galaxy dump, WITHOUT storing the dump.

Run on your own PC (needs the internet; the dump is ~80 GB but is only streamed through, never saved):
    python tools/build_neutron_list.py https://downloads.spansh.co.uk/galaxy.json.gz
or from a file you already have:
    python tools/build_neutron_list.py galaxy.json.gz
Writes data/neutron_stars.csv.gz (name,x,y,z,id64). Safe to stop with Ctrl+C: it writes what it has so far.
Check Spansh's terms before sharing the result with anyone."""
import csv
import gzip
import json
import sys
import urllib.request

PREFILTER = b'"Neutron Star"'


def stream(source):
    if str(source).startswith(("http://", "https://")):
        request = urllib.request.Request(source, headers={"User-Agent": "Starling-neutron-list"})
        return gzip.GzipFile(fileobj=urllib.request.urlopen(request, timeout=60))
    return gzip.open(source, "rb")


def neutron_systems(lines):
    """Yield (name, x, y, z, id64) for each system line that has a neutron star. One system per line."""
    for line in lines:
        if PREFILTER not in line:                  # cheap test first: almost every line stops here
            continue
        text = line.strip().rstrip(b",")
        if not text.startswith(b"{"):
            continue
        try:
            system = json.loads(text)
            coords = system["coords"]
        except (ValueError, KeyError, TypeError):
            continue
        if any(isinstance(b, dict) and b.get("subType") == "Neutron Star" for b in system.get("bodies") or []):
            yield system.get("name"), coords["x"], coords["y"], coords["z"], system.get("id64", "")


def build(source, out_path, progress=None):
    count = seen = 0
    with gzip.open(out_path, "wt", encoding="utf-8", newline="") as out:
        writer = csv.writer(out)
        counter = {"n": 0}

        def lines():
            for line in stream(source):
                counter["n"] += 1
                if progress and counter["n"] % 1000000 == 0:
                    progress(counter["n"], count)
                yield line
        try:
            for row in neutron_systems(lines()):
                writer.writerow(row)
                count += 1
        except KeyboardInterrupt:
            print("Stopped early; keeping what was found.")
    return count


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    target = sys.argv[2] if len(sys.argv) > 2 else "data/neutron_stars.csv.gz"
    found = build(sys.argv[1], target, lambda n, c: print("%d million systems read, %d neutron systems so far" % (n // 1000000, c)))
    print("Done: %d neutron systems written to %s" % (found, target))
