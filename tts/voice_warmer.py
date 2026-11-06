"""
VOICE WARMER - quietly gets her new lines ready so she never has to make them up on the spot.

Her voice engine (Kokoro) is slow on a CPU: a sentence that is NOT in the voice cache takes a second or two to make
before she can start talking. Every update that adds lines adds sentences that are not cached yet. This helper makes them
in the background, one at a time, and only when it will not get in the way:
  * the game is not running / you are in a menu / you are docked (so the CPU is free), and
  * she is not talking and nothing has been said for a few seconds.
Most-used lines are made first (jumps, docking, combat), the rest after. It is safe to stop at any moment, and lines that
are already made are skipped instantly. Switch it off with  tts.warm_cache = "off"  (dashboard: Voice page).
"""
import threading
import time

from core.logger import get_logger
from tts.kokoro_tts import speed_from_rate
from tts.voice_cache_builder import collect_texts

log = get_logger("voice_warmer")

FIRST = ("FSDJump", "Docked", "Undocked", "SupercruiseEntry", "SupercruiseExit", "StartJump", "DockingGranted", "Touchdown",
         "Liftoff", "FuelScoopComplete", "UnderAttack", "ShieldsDown", "ShieldsUp", "Bounty", "Died", "HardpointsDeployed",
         "ShipyardSwap", "Combat_", "ChitChat", "Talk_", "Lore_")
PAUSE_BETWEEN_SECONDS = 1.0       # a rest between sentences, so the CPU is never flat out
QUIET_BEFORE_SECONDS = 6.0        # nothing spoken for this long before it makes the next one
CHECK_SECONDS = 20.0              # how often it looks again when it has to wait


def priority_order(dialogue, allow_mature, settings):
    """Every fixed sentence, the most-used keys first."""
    ordered, seen = [], set()

    def add(texts):
        for text in texts:
            if text not in seen:
                seen.add(text)
                ordered.append(text)

    from core.identity import personalise
    for wanted in FIRST:
        for key, lines in dialogue.lines.items():
            if key.startswith(wanted):
                add(t for t in _texts(lines, allow_mature, settings, personalise))
    add(collect_texts(dialogue, allow_mature, settings))
    if settings is None or settings.get("tts.warm_mining", True):
        add(mining_texts(dialogue, allow_mature, settings))
    return ordered


MINING_MATERIAL_KEYS = ("Refined_FirstTop", "Refined_FirstGood", "Refined_Cheer", "Prospected_Motherlode")
MINING_COUNT_KEYS = ("Refined_Milestone",)
MINING_MAX_COUNT = 20          # tonnes of one mineral she pre-makes the count lines for


def mining_texts(dialogue, allow_mature, settings):
    """The mining lines with a mineral name or a tonne count, made for your favourite minerals ahead of time.

    They are the lines that used to start 2 or 3 seconds late (every one had to be made on the spot). Only the minerals she gets
    excited about (your favourites) and the first few counts she calls out (every 3, 5 or 10 tonnes, up to 20). Kept small on purpose:
    every extra line is more waiting the first time."""
    try:
        from core.identity import personalise
        from mining import minerals
        step = {"quiet": 10, "chatty": 3}.get(str(minerals.option("chatter", "normal")), 5)
        names = sorted({minerals.spoken(k) for k in minerals.favourites()})
        counts = list(range(step, MINING_MAX_COUNT + 1, step))
    except Exception:
        return []

    def fill(keys, fields_list):
        for key in keys:
            for line in dialogue.lines.get(key, []):
                if line.mature and not allow_mature:
                    continue
                for fields in fields_list:
                    try:
                        text = personalise(line.text, settings).format_map(fields)
                    except (KeyError, IndexError, ValueError):
                        continue
                    for part in (p.strip() for p in text.split("||")):
                        if part and "{" not in part:
                            yield part

    class Fields(dict):
        def __missing__(self, key):
            raise KeyError(key)

    out = list(fill(MINING_MATERIAL_KEYS, [Fields(Material=n) for n in names]))
    out += list(fill(MINING_COUNT_KEYS, [Fields(Material=n, Count=c) for c in counts for n in names]))
    return out


def _texts(lines, allow_mature, settings, personalise):
    for line in lines:
        if line.mature and not allow_mature:
            continue
        for text in (part.strip() for part in personalise(line.text, settings).split("||")):
            if text and "{" not in text:
                yield text


class VoiceWarmer:
    def __init__(self, kokoro, dialogue, settings, speech=None, clock=time.monotonic, sleep=time.sleep,
                 free_provider=None):
        self.kokoro = kokoro
        self.dialogue = dialogue
        self.settings = settings
        self.speech = speech
        self.clock = clock
        self.sleep = sleep
        self.free_provider = free_provider or (lambda: True)      # True when the CPU is free (game not busy)
        self.made = 0
        self.skipped = 0
        self.failed = 0
        self.total = 0
        self.finished = False
        self.started_at = None             # when the lines started being made (for the time estimate)
        self.force = False                 # "prepare her voice now": ignore the free-CPU rule
        self._stop = threading.Event()
        self._thread = None

    def mode(self):
        return str(self.settings.get("tts.warm_cache", "idle")).lower()

    def start(self):
        if self._thread is None and self.kokoro is not None:
            self._thread = threading.Thread(target=self._run, name="voice-warmer", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    def run_now(self):
        """The dashboard button: get everything ready as fast as possible."""
        self.force = True
        self.finished = False
        self.start()

    def may_work(self):
        if self.force:
            return True
        if self.mode() == "off" or not self.free_provider():
            return False
        return not (self.speech is not None and self.speech.is_busy())

    def _run(self):
        try:
            if not self.kokoro.wait_until_loaded(1800) or self._stop.is_set():
                return
            speed = speed_from_rate(self.settings.get("tts.rate", 0))
            texts = priority_order(self.dialogue, bool(self.settings.get("speech.allow_mature", False)), self.settings)
            self.total = len(texts)
            self.started_at = self.clock()
            quiet_since = self.clock()
            for text in texts:
                if self._stop.is_set():
                    return
                if self.kokoro.is_cached(text, speed):
                    self.skipped += 1
                    continue
                while not self._stop.is_set() and not self.may_work():
                    quiet_since = self.clock()
                    self.sleep(CHECK_SECONDS if not self.force else 0.5)
                if self._stop.is_set():
                    return
                if not self.force and self.clock() - quiet_since < QUIET_BEFORE_SECONDS:
                    self.sleep(QUIET_BEFORE_SECONDS)
                if self.kokoro.render(text, speed):
                    self.made += 1
                else:
                    self.failed += 1
                if not self.force:
                    self.sleep(PAUSE_BETWEEN_SECONDS)
            log.info("Voice warm-up finished: %d made, %d already there, %d failed", self.made, self.skipped, self.failed)
        except Exception:
            log.exception("The voice warm-up stopped")
        finally:
            self.finished = True
            self.force = False
            self._thread = None

    def running(self):
        return self._thread is not None and not self.finished

    def progress(self):
        """(lines ready, total lines, seconds left or None). Used by the dashboard's progress bar."""
        done = self.made + self.skipped + self.failed
        if not self.total:
            return 0, 0, None
        left = None
        if self.made >= 3 and self.started_at is not None:
            per_line = (self.clock() - self.started_at) / float(self.made)
            remaining = max(0, self.total - done)
            left = remaining * per_line
        return min(done, self.total), self.total, left

    def status(self):
        if self.mode() == "off" and not self.force:
            return "Voice preparation is switched off."
        if self.finished or (self.total and self.made + self.skipped + self.failed >= self.total):
            return "Her voice is fully prepared (%d new lines made)." % self.made
        if self.total:
            return "Preparing her voice: %d of %d lines ready." % (self.made + self.skipped, self.total)
        return "Waiting for her voice to load."
