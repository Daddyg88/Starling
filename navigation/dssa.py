"""
The Deep Space Support Array (DSSA): fleet carriers parked around the galaxy, with services for explorers.

"Plot me a route to the nearest DSSA in the Norma Expanse": this file knows where the carriers are and which one is nearest.
The list comes from EDAstro (https://edastro.com/mapcharts/files/DSSAdeployments.csv, a community list updated daily), is saved
in data/dssa_cache.json and refreshed when it is more than 12 hours old (the old copy is used if EDAstro can't be reached).
Carriers move, so the list is only as fresh as EDAstro's.

The columns of that CSV are found by their names, not their order (EDAstro says they can change). If the CSV has no coordinates,
the system's coordinates are asked from Spansh (once, then kept in the cache).
"""

import csv
import io
import json
import re
import time
import urllib.error
import urllib.request
from core.secure_open import open_url
from pathlib import Path

from core.logger import get_logger
from navigation.edastro import distance
from navigation.regions import find_region
from navigation.region_data import regions

log = get_logger("dssa")

URLS = ("https://edastro.com/mapcharts/files/DSSAdeployments.csv", "https://edastro.com/mapcharts/files/edsmPOI.csv")
USER_AGENT = "Starling (Elite Dangerous companion; DSSA finder)"
MAX_AGE = 12 * 3600
TIMEOUT = 20
MAX_BYTES = 4_000_000

_SYSTEM_FIRST = ("current system", "currentsystem", "system", "starsystem", "star system", "current location", "location", "galmapsearch")
_NOT_SYSTEM = re.compile(r"dest|next|target|plan|origin|from|previous|prev")
_GONE = re.compile(r"decommission|retire|lost|destroy|scrap|cancel|removed|offline")
_MISHEARD = re.compile(r"\b(?:d ?s ?s ?a|dss a|d s a|dsa|disa|dissa|dessa|dee ess ess ay|de sa|desa|the sa)\b")
_GO = re.compile(r"\b(?:plot|take|bring|fly|get|navigate|head|go|set|route|lead|find|show)\b")
_FILLER = re.compile(r"\b(?:in|at|near|around|within|of|the|a|an|to|for|from|me|please|carrier|carriers|nearest|closest|closer|next|route|course|my|us|and|can|you|region|area|galaxy|space)\b")


def parse_request(said):
    """('', ) is not a DSSA request -> None. Otherwise the region words she heard ('' = anywhere). Handles 'nearest DSSA in the Norma Expanse'."""
    said = _MISHEARD.sub("dssa", " ".join(str(said or "").lower().split()))
    if "dssa" not in said or not _GO.search(said):
        return None
    tail = said.split("dssa", 1)[1]
    tail = " ".join(_FILLER.sub(" ", tail).split())
    if not tail and " in " in said.split("dssa", 1)[0]:         # "plot a route in the norma expanse to the nearest dssa"
        tail = " ".join(_FILLER.sub(" ", said.split("dssa", 1)[0].split(" in ", 1)[1]).split())
    return tail


def _key(text):
    text = re.sub(r"\b(the|a|an)\b", " ", str(text or "").lower())
    return re.sub(r"[^a-z]", "", text)


def find_region_named(words):
    """The region whose name is in these words ('norma expanse' -> 'Norma Expanse'), longest name first, else None."""
    wanted = _key(words)
    if not wanted:
        return None
    best = None
    for name in regions:
        if not name:
            continue
        k = _key(name)
        if k and (k in wanted or (len(wanted) >= 5 and wanted in k)):
            if best is None or len(k) > len(_key(best)):
                best = name
    return best


def _clean_system(value):
    return " ".join(str(value or "").split())


def parse_csv(text):
    """Rows of {"name", "system", "pos"} (pos may be None) from EDAstro's CSV. Finds the columns by their names."""
    try:
        sample = text[:2000]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample else csv.excel
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [r for r in reader if any(c.strip() for c in r)]
    if len(rows) < 2:
        return []
    head = [h.strip().lower() for h in rows[0]]

    def col(*names):
        for n in names:
            if n in head:
                return head.index(n)
        return None

    sys_i = col(*_SYSTEM_FIRST)
    if sys_i is None:
        for i, h in enumerate(head):
            if "system" in h and not _NOT_SYSTEM.search(h):
                sys_i = i
                break
    name_i = col("name", "carrier", "carrier name", "carriername", "poi", "title")
    if name_i is None:
        for i, h in enumerate(head):
            if ("name" in h or "carrier" in h) and i != sys_i:
                name_i = i
                break
    status_i = next((i for i, h in enumerate(head) if h in ("status", "state") or "status" in h), None)
    xyz = []
    for axis in "xyz":
        xyz.append(next((i for i, h in enumerate(head) if re.search(r"(^|[^a-z])%s$" % axis, h) and "id" not in h), None))
    coord_i = next((i for i, h in enumerate(head) if h in ("coordinates", "coords", "coord")), None)
    out, seen = [], set()
    for row in rows[1:]:
        def cell(i):
            return row[i].strip() if i is not None and i < len(row) else ""
        system = _clean_system(cell(sys_i))
        name = _clean_system(cell(name_i))
        if not system or (status_i is not None and _GONE.search(cell(status_i).lower())):
            continue
        pos = None
        if all(i is not None for i in xyz):
            try:
                pos = tuple(float(cell(i)) for i in xyz)
            except ValueError:
                pos = None
        if pos is None and coord_i is not None:
            nums = re.findall(r"-?\d+(?:\.\d+)?", cell(coord_i))
            if len(nums) == 3:
                pos = tuple(float(n) for n in nums)
        key = (name or system).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name or system, "system": system, "pos": list(pos) if pos else None})
    return out


class Dssa:
    def __init__(self, cache_file=None, spansh=None, opener=None, clock=time.time):
        self.cache_file = Path(cache_file) if cache_file else None
        self.spansh = spansh
        self._open = opener or open_url
        self.clock = clock
        self.carriers = []
        self.loaded_at = 0.0
        self._load_cache()

    # ---- the list ----
    def _load_cache(self):
        try:
            data = json.loads(self.cache_file.read_text(encoding="utf-8")) if self.cache_file and self.cache_file.exists() else {}
        except (OSError, ValueError):
            data = {}
        self.carriers = [c for c in data.get("carriers", []) if isinstance(c, dict) and c.get("system")]
        self.loaded_at = float(data.get("at") or 0)

    def _save_cache(self):
        if not self.cache_file:
            return
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            self.cache_file.write_text(json.dumps({"at": self.loaded_at, "carriers": self.carriers}), encoding="utf-8")
        except OSError:
            log.warning("Could not save the DSSA list", exc_info=True)

    def _download(self):
        for url in URLS:
            try:
                request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with self._open(request, timeout=TIMEOUT) as reply:
                    text = reply.read(MAX_BYTES).decode("utf-8", "replace")
            except (urllib.error.URLError, OSError, TimeoutError, ValueError) as error:
                log.info("Could not read %s: %s", url, error)
                continue
            rows = parse_csv(text)
            if "edsmpoi" in url.lower():                    # the big all-purpose list: keep only the DSSA ones
                rows = [r for r in rows if "dssa" in r["name"].lower() or "dssa" in r["system"].lower()]
            if rows:
                return rows
        return None

    def refresh(self, force=False):
        """True when we have a list (fresh, or the old one if EDAstro can't be reached)."""
        if self.carriers and not force and self.clock() - self.loaded_at < MAX_AGE:
            return True
        rows = self._download()
        if rows:
            old = {c["system"].lower(): c.get("pos") for c in self.carriers}
            for r in rows:
                if r["pos"] is None:
                    r["pos"] = old.get(r["system"].lower())       # keep coordinates we already looked up
            self.carriers, self.loaded_at = rows, self.clock()
            self._save_cache()
        return bool(self.carriers)

    def _fill_positions(self, wanted):
        """Asks Spansh for the coordinates of carriers that have none (only those we need to compare)."""
        changed = False
        for c in wanted:
            if c.get("pos") is None and self.spansh is not None:
                try:
                    pos = self.spansh.coordinates(c["system"])
                except Exception:
                    pos = None
                if pos:
                    c["pos"] = list(pos)
                    changed = True
        if changed:
            self._save_cache()

    # ---- asking ----
    def nearest(self, here, region=None):
        """(carrier dict, light years) nearest to `here` (x, y, z), optionally inside a region, or None."""
        if not self.carriers or here is None:
            return None
        self._fill_positions([c for c in self.carriers if c.get("pos") is None])
        best = None
        for c in self.carriers:
            pos = c.get("pos")
            if not pos:
                continue
            if region:
                found = find_region(*pos)
                if not found or found[1] != region:
                    continue
            d = distance(here, pos)
            if best is None or d < best[1]:
                best = (c, d)
        return best
