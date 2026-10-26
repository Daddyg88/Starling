"""
"Learn from my old journals": reads every Elite journal file once, quietly, in the background.

What she picks up (nothing is spoken while she reads, and nothing is sent anywhere):
  * which biological species are already in your codex          -> the white flags on the overlay
  * every surface scan: which genera were really on which kind of planet -> better exobiology guesses (BioLearned)
  * the real prices from your old biological data sales          -> exact value estimates

It reads line by line (never a whole file in memory), only looks at the few lines it needs, and pauses between files so the game
and the stream are not disturbed. Each planet is counted once, so running it again later only adds what is new.
"""

import json
import threading
import time
from pathlib import Path

from core.logger import get_logger
from journal.bio_predict import BioPredictor, load_rules
from journal.exobiology import _write_json
from memory.keeper import BIG_MISSION, credits

log = get_logger("history_scan")

WANTED = (b'"event":"Statistics"', b'"event":"Died"', b'"event":"MissionCompleted"', b'"event":"SellExplorationData"', b'"event":"MultiSellExplorationData"',
          b'"event":"ColonisationSystemClaim"', b'"event":"ColonisationSystemClaimRelease"', b'"event":"Scan"', b'"event":"FSDJump"', b'"event":"Location"', b'"event":"CarrierJump"', b'"event":"FSSBodySignals"',
          b'"event":"SAASignalsFound"', b'"event":"CodexEntry"', b'"event":"ScanOrganic"', b'"event":"SellOrganicData"')
PAUSE_BETWEEN_FILES = 0.05


class HistoryScan:
    def __init__(self, folder_provider, codex, learned, tracker, summary_file=None, store=None, owned=None):
        self.folder_provider = folder_provider
        self.codex = codex
        self.learned = learned
        self.tracker = tracker
        self.summary_file = Path(summary_file) if summary_file else None
        self.store = store            # her memory (memory/store.py), optional
        self.owned = owned            # the systems you own (journal/owned_systems.py), optional
        self.running = False
        self.stop_flag = False
        self.files_done = 0
        self.files_total = 0
        self.summary = {}
        self.message = ""
        self._thread = None

    # ---- control ----
    def start(self):
        """Starts reading in the background. Returns a sentence for the screen."""
        if self.running:
            return "Already reading your journals."
        folder = self.folder_provider()
        if not folder:
            return "I can't find your Elite journal folder yet. Start the game once, or set the folder on the Developer page."
        self.running, self.stop_flag = True, False
        self.files_done = self.files_total = 0
        self.message = "Starting..."
        self._thread = threading.Thread(target=self._run, args=(Path(folder),), name="history-scan", daemon=True)
        self._thread.start()
        return "Reading your journals in the background. You can keep playing."

    def stop(self):
        self.stop_flag = True

    def status(self):
        if self.running:
            return "Reading journals: %d of %d. %s" % (self.files_done, self.files_total, self.message)
        return self.message

    # ---- the work ----
    def _run(self, folder):
        try:
            self.summary = self.read_folder(folder)
            self.message = self.describe(self.summary)
        except Exception:
            log.exception("Reading the old journals failed")
            self.message = "Something went wrong while reading the journals (it is in the log)."
        finally:
            self.running = False

    def read_folder(self, folder):
        files = sorted(Path(folder).glob("Journal*.log"))
        self.files_total = len(files)
        predictor = BioPredictor(self.tracker, self.codex, None, load_rules(), self.learned)   # a private copy: it speaks to nobody
        names = {r["n"].lower() for r in predictor.rules}
        before = (len(self.codex.known), len(self.learned.seen), len(self.tracker.learned))
        totals = {"journals": 0, "lines": 0, "seconds": 0.0, "jumps": 0, "missions": 0, "deaths": 0, "claims": 0}
        self._species_seen = set()
        prices = {}
        for file in files:
            if self.stop_flag:
                break
            self._read_file(file, predictor, names, prices, totals)
            self.files_done += 1
            self.message = "Species in your codex so far: %d." % len(self.codex.known)
            time.sleep(PAUSE_BETWEEN_FILES)
        for species, value in prices.items():
            self.tracker.learned[species.lower()] = int(value)
        if prices:
            _write_json(self.tracker._learned_file, self.tracker.learned) if self.tracker._learned_file else None
        if not self.stop_flag:
            self.codex.history_done = True
        self.codex.save()
        self.learned.save()
        if totals.get("played"):
            totals["seconds"] = totals["played"]  # the game's own play time is exact; the file span can include a game left running
        self._remember(totals)
        out = {"journals": totals["journals"], "lines": totals["lines"], "stopped": self.stop_flag,
               "species": len(self.codex.known) - before[0], "species_total": len(self.codex.known),
               "planets": len(self.learned.seen) - before[1], "prices": len(self.tracker.learned) - before[2],
               "finished": time.strftime("%Y-%m-%d %H:%M"),
               "hours": round(totals["seconds"] / 3600.0, 1), "jumps": totals["jumps"], "missions": totals["missions"],
               "deaths": totals["deaths"], "owned": len(self.owned.systems) if self.owned else 0}
        if self.summary_file:
            _write_json(self.summary_file, out)
        return out

    def _read_file(self, file, predictor, names, prices, totals):
        predictor.reset()
        totals["journals"] += 1
        try:
            handle = open(file, "rb")
        except OSError:
            return
        first = last = b""
        with handle:
            for raw in handle:
                if not first:
                    first = raw
                last = raw
                if not any(tag in raw for tag in WANTED):
                    continue
                totals["lines"] += 1
                try:
                    entry = json.loads(raw)
                except ValueError:
                    continue
                self._entry(entry, predictor, names, prices, totals)
        span = _seconds_between(first, last)
        if span:
            totals["seconds"] += span

    def _entry(self, entry, predictor, names, prices, totals):
        self._bio(entry, predictor, names, prices)
        self._life(entry, predictor.system, totals)
        if entry.get("event") == "Statistics":
            played = (entry.get("Exploration") or {}).get("Time_Played")
            if isinstance(played, (int, float)) and played > totals.get("played", 0):
                totals["played"] = played

    def _life(self, entry, system, totals):
        """Her other memories: counters, records, deaths, big missions, first samples and the systems you own."""
        kind, store = entry.get("event"), self.store
        if kind == "FSDJump":
            totals["jumps"] += 1
            dist = entry.get("JumpDist")
            if store and isinstance(dist, (int, float)) and dist > 0 and entry.get("StarSystem"):
                store.set_record("longest_jump", "your longest jump, %.1f light years, into %s" % (dist, entry["StarSystem"]), dist, entry["StarSystem"])
        elif kind == "MissionCompleted":
            totals["missions"] += 1
            reward, name = entry.get("Reward") or 0, entry.get("LocalisedName")
            if store and isinstance(reward, (int, float)) and reward >= BIG_MISSION and name:
                store.add("big_mission", "a mission worth %s: %s" % (credits(reward), name), system, importance=2)
        elif kind == "Died":
            totals["deaths"] += 1
            if store:
                killer = entry.get("KillerName")
                store.add("death", "You were destroyed" + (" by %s" % killer if killer else "") + (" in %s" % system if system else ""), system, importance=2)
        elif kind == "SellOrganicData":
            total = entry.get("TotalValue") or sum((i.get("Value") or 0) + (i.get("Bonus") or 0) for i in entry.get("BioData") or [] if isinstance(i, dict))
            if store and total > 0:
                store.set_record("biggest_organic_sale", "your biggest biology sale, %s" % credits(total), total, system)
        elif kind in ("SellExplorationData", "MultiSellExplorationData"):
            total = entry.get("TotalEarnings") or 0
            if store and total > 0:
                store.set_record("biggest_exploration_sale", "your biggest exploration sale, %s" % credits(total), total, system)
        elif kind == "ScanOrganic" and entry.get("ScanType") == "Log":
            species = entry.get("Species_Localised") or entry.get("Genus_Localised")
            if store and species and species not in self._species_seen:
                self._species_seen.add(species)
                store.add("first_species", "the first time you sampled %s" % species, system)
        elif kind == "ColonisationSystemClaim" and self.owned:
            self.owned.claim(entry.get("StarSystem"), entry.get("SystemAddress"), entry.get("timestamp"))
        elif kind == "ColonisationSystemClaimRelease" and self.owned:
            self.owned.release(entry.get("StarSystem"))

    def _remember(self, totals):
        """Counters only go up, and the game the live memory counted is part of the journals, so take the larger number."""
        if not self.store or self.stop_flag:
            return
        for stat, value in (("hours_together", round(totals["seconds"] / 3600.0, 4)), ("systems_visited", totals["jumps"]),
                            ("missions_completed", totals["missions"]), ("times_destroyed", totals["deaths"])):
            self.store.raise_stat(stat, value)

    def _bio(self, entry, predictor, names, prices):
        kind = entry.get("event")
        if kind in ("FSDJump", "Location", "CarrierJump"):
            predictor.set_system(entry.get("StarSystem"))
        elif kind == "Scan":
            predictor.note_scan(entry)
        elif kind == "FSSBodySignals":
            predictor.note_fss(entry, predictor.system)
        elif kind == "SAASignalsFound":
            predictor.note_saa(entry, predictor.system)
        elif kind in ("CodexEntry", "ScanOrganic"):
            self.codex._from_entry(entry, names, save=False)
        elif kind == "SellOrganicData":
            for item in entry.get("BioData") or []:
                if isinstance(item, dict) and item.get("Species_Localised") and isinstance(item.get("Value"), (int, float)) and item["Value"] > 0:
                    prices[str(item["Species_Localised"])] = item["Value"]       # later sales overwrite earlier ones

    @staticmethod
    def describe(s):
        text = "Read %d journal files%s." % (s["journals"], " (stopped early)" if s.get("stopped") else "")
        text += " %d codex species known (%d new to me)." % (s["species_total"], s["species"])
        text += " Learned from %d surface scans and %d real prices." % (s["planets"], s["prices"])
        text += " About %.0f hours played, %d jumps, %d missions, %d deaths." % (s.get("hours", 0), s.get("jumps", 0), s.get("missions", 0), s.get("deaths", 0))
        if s.get("owned"):
            text += " You own %d system%s." % (s["owned"], "" if s["owned"] == 1 else "s")
        return text


def _seconds_between(first, last):
    """Seconds between the first and last journal line of a file (0 if the stamps can't be read)."""
    def stamp(raw):
        i = raw.find(b'"timestamp":"')
        if i < 0:
            return None
        try:
            return time.mktime(time.strptime(raw[i + 13:i + 32].decode("ascii"), "%Y-%m-%dT%H:%M:%S"))
        except (ValueError, UnicodeDecodeError):
            return None
    a, b = stamp(first), stamp(last)
    return max(0.0, b - a) if a is not None and b is not None else 0.0
