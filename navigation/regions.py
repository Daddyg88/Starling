"""
REGIONS: she announces the galaxy region you jump into, and says when it is your first time there.

The region comes from the system's galaxy coordinates (StarPos in the journal) and a map of the 42 regions
(navigation/region_data.py, by Ben Peddell, MIT licence). Which regions you have visited is kept in
data/regions_visited.json. The first time she runs she reads your old journal files ONCE (on a background thread)
to fill that list, so she doesn't call every region you already know "new".

Nothing is said when the game loads (that is only where you start), only on a jump (or a carrier jump) into another region.
"""

import json
import re
import threading
from pathlib import Path

from core import paths
from core.logger import get_logger
from navigation.region_data import regionmap, regions

log = get_logger("regions")

X0, Z0 = -49985, -24105
_POS = re.compile(r'"StarPos"\s*:\s*\[\s*(-?[\d.eE+-]+)\s*,\s*(-?[\d.eE+-]+)\s*,\s*(-?[\d.eE+-]+)\s*\]')


def find_region(x, y, z):
    """(number, name) of the region at these galaxy coordinates, or None if outside the map."""
    px = int((x - X0) * 83 / 4096)
    pz = int((z - Z0) * 83 / 4096)
    if px < 0 or pz < 0 or pz >= len(regionmap):
        return None
    value, start = 0, 0
    for run, v in regionmap[pz]:
        if px < start + run:
            value = v
            break
        start += run
    return (value, regions[value]) if value else None


def region_of(pos):
    if not pos or len(pos) != 3:
        return None
    try:
        return find_region(float(pos[0]), float(pos[1]), float(pos[2]))
    except (TypeError, ValueError):
        return None


def scan_journals(folder):
    """Every region any old journal file mentions (by the StarPos of each line). Returns a set of region numbers."""
    found = set()
    try:
        files = sorted(Path(folder).glob("Journal*.log"))
    except OSError:
        return found
    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if "StarPos" not in line:
                        continue
                    match = _POS.search(line)
                    if match:
                        region = find_region(*(float(v) for v in match.groups()))
                        if region:
                            found.add(region[0])
        except OSError:
            continue
    return found


class RegionTracker:
    def __init__(self, bus, narrator, settings, state_provider, journal_folder=None, visited_file=None, spawn=None):
        self.bus = bus
        self.narrator = narrator
        self.settings = settings
        self.state_provider = state_provider
        self.journal_folder = journal_folder
        self.file = Path(visited_file) if visited_file else paths.DATA_DIR / "regions_visited.json"
        self.spawn = spawn or self._thread
        self.current = None                      # region number we are in now
        self.visited = self._load()
        self._lock = threading.Lock()
        self._scanning = False

    @staticmethod
    def _thread(function):
        threading.Thread(target=function, name="region-scan", daemon=True).start()

    # ---- wiring ----
    def attach(self):
        here = region_of(getattr(self.state_provider(), "star_pos", None))
        if here:
            self.current = here[0]
        self.bus.subscribe("FSDJump", self.on_jump)
        self.bus.subscribe("CarrierJump", self.on_jump)
        self.bus.subscribe("Location", self.on_location)
        if self.visited is None:
            self.visited = set()
            if self.journal_folder is not None:
                self._scanning = True
                self.spawn(self._first_scan)
            elif here:
                self.visited.add(here[0])
                self._save()

    def detach(self):
        for name, callback in (("FSDJump", self.on_jump), ("CarrierJump", self.on_jump), ("Location", self.on_location)):
            self.bus.unsubscribe(name, callback)

    def enabled(self):
        return bool(self.settings.get("regions.announce", True))

    # ---- what happens ----
    def _first_scan(self):
        try:
            old = scan_journals(self.journal_folder)
        except Exception:
            log.exception("Could not read the old journals for regions")
            old = set()
        with self._lock:
            self.visited |= old
            if self.current:
                self.visited.add(self.current)
            self._scanning = False
        self._save()
        log.info("Regions you have already visited: %d", len(self.visited))

    def on_location(self, _event=None):
        """Loading the game: just remember where we are. Nothing is announced."""
        here = region_of(getattr(self.state_provider(), "star_pos", None))
        if here:
            self.current = here[0]
            self._mark(here[0])

    def on_jump(self, _event=None):
        here = region_of(getattr(self.state_provider(), "star_pos", None))
        if not here:
            return None
        number, name = here
        if number == self.current:
            return None
        first_time = False
        with self._lock:
            known = self.visited is not None and number in self.visited and not self._scanning
            first_time = not known and not self._scanning
            self.current = number
        self._mark(number)
        if not self.enabled():
            return None
        if self._scanning:
            self.narrator.say("RegionEntered", {"region": name})      # not sure yet if it is new: say only where we are
            return "entered"
        self.narrator.say("RegionFirst" if first_time else "RegionEntered", {"region": name})
        return "first" if first_time else "entered"

    def _mark(self, number):
        with self._lock:
            if self.visited is None or number in self.visited:
                return
            self.visited.add(number)
            scanning = self._scanning
        if not scanning:
            self._save()

    # ---- remembering ----
    def _load(self):
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
            return {int(n) for n in data.get("visited", [])}
        except (OSError, ValueError, AttributeError, TypeError):
            return None

    def _save(self):
        try:
            self.file.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                data = {"visited": sorted(self.visited or [])}
            self.file.write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            log.exception("Could not save the visited regions")
