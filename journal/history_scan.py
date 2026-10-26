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

log = get_logger("history_scan")

WANTED = (b'"event":"Scan"', b'"event":"FSDJump"', b'"event":"Location"', b'"event":"CarrierJump"', b'"event":"FSSBodySignals"',
          b'"event":"SAASignalsFound"', b'"event":"CodexEntry"', b'"event":"ScanOrganic"', b'"event":"SellOrganicData"')
PAUSE_BETWEEN_FILES = 0.05


class HistoryScan:
    def __init__(self, folder_provider, codex, learned, tracker, summary_file=None):
        self.folder_provider = folder_provider
        self.codex = codex
        self.learned = learned
        self.tracker = tracker
        self.summary_file = Path(summary_file) if summary_file else None
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
        totals = {"journals": 0, "lines": 0}
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
        out = {"journals": totals["journals"], "lines": totals["lines"], "stopped": self.stop_flag,
               "species": len(self.codex.known) - before[0], "species_total": len(self.codex.known),
               "planets": len(self.learned.seen) - before[1], "prices": len(self.tracker.learned) - before[2],
               "finished": time.strftime("%Y-%m-%d %H:%M")}
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
        with handle:
            for raw in handle:
                if not any(tag in raw for tag in WANTED):
                    continue
                totals["lines"] += 1
                try:
                    entry = json.loads(raw)
                except ValueError:
                    continue
                self._entry(entry, predictor, names, prices)

    def _entry(self, entry, predictor, names, prices):
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
        return text
