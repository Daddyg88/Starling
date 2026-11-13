"""THE HACK (0.96.3): a short game that maps a settlement for the East Orion Company.

The story: the EOC want every Odyssey base on file and Starling is the only one who knows how to do it. The truth: while the "hack"
runs, every few seconds she looks at the radar in the corner of the screen (navigation/radar_read.py), turns the terminals, gun posts and
ammo and recharge points she sees into real positions, and keeps them (navigation/radar_points.py). Those positions are what we need to
correct the settlement maps and to place you on them. Nothing is sent anywhere: the data goes into the diagnostics zip like everything else.

Say "start hack" (or "hack the base") on foot at a settlement. She takes a radar picture every few seconds for up to ten minutes,
says how it is going, and a small progress panel shows on the screen (ui/hack_overlay.py) with an old modem sound. When enough of the
base has been seen she says so, tells you what she thinks the layout is, tells you the next chapter of her story, lifts her mood a little,
and suggests the next base to hack. "stop hack" ends it early; what she saw is kept.
It never presses a key and never touches the game. It needs Elite in Windowed or Borderless mode.

When you step out near a base nobody has mapped she says so once and explains what to do.
"""
import math
import re
import threading
import time

from core.logger import get_logger
from navigation import radar_match, radar_read

log = get_logger("hack")

TICK_SECONDS = 4.0
MAX_SECONDS = 600.0                 # a hack ends by itself after ten minutes
MIN_PICTURES = 10                   # it can only finish after this many radar pictures
GOOD_ENOUGH = 0.72                  # ...or, after GOOD_ENOUGH_SECONDS, once this much is done (a detector can miss one terminal for ever)
GOOD_ENOUGH_SECONDS = 420.0
TARGET_CELLS = 30                   # 12 m squares walked: about 4 minutes of walking round a base
EXPECTED_TERMINALS = 7              # when the layout is not known (the layouts have 2 to 11, most 5 to 9)
EXTRAS_TARGET = 4                   # ammo, recharge and gun posts she wants to have seen
MILESTONES = (0.25, 0.50, 0.75)
FAILS_BEFORE_GIVING_UP = 6          # radar not found this many pictures in a row: she says so and stops
SHOWN_AFTER_SECONDS = 14.0          # the finished panel stays up this long
NEED_REMINDER_SECONDS = 75.0
HACK_POINTS = 6.0                   # her mood score goes up by this much (in Automatic mood only)
MAPPED_MIN_TERMINALS = 5
MAPPED_MIN_PICTURES = 15

_START = re.compile(r"^(?:(?:start|begin|run|do|launch|commence) (?:the |a |this |that )?(?:hack|scan|survey|mapping)(?: (?:of )?(?:the |this |that )?(?:base|settlement|site|place))?"
                    r"|hack (?:the |this |that )?(?:base|settlement|site|place)(?: for the (?:eoc|east orion company))?"
                    r"|(?:map|survey) (?:the |this |that )?(?:base|settlement|site|place)"
                    r"|(?:start|begin) (?:the )?(?:eoc )?mapping (?:mission|job|run))$")
_STOP = re.compile(r"^(?:(?:stop|abort|cancel|end|halt) (?:the |this )?(?:hack|scan|survey|mapping)|hack (?:stop|abort|cancel)|that will do|that is enough for the hack)$")
_STATUS = re.compile(r"^(?:how(?: is| s) the (?:hack|scan|survey|mapping)(?: going)?|hack (?:status|progress)|(?:what is|what s) the hack (?:status|progress))$")
_THIS_IS = re.compile(r"^(?:this|that|the) (?:base|settlement|site|place) is (?:an? )?(?P<what>.+)$")


def clean(text):
    text = re.sub(r"[^a-z0-9 ]", " ", str(text or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def progress_of(counts, twice, cells, expected_terminals):
    """How much of the hack is done (0 to 1) and the checklist: [(label, found, needed)].
    counts = {kind: how many points}, twice = terminals seen at least twice, cells = 12 m squares walked."""
    expected = max(2, int(expected_terminals or EXPECTED_TERMINALS))
    terminals = counts.get("terminal", 0)
    extras = counts.get("ammo", 0) + counts.get("recharge", 0) + counts.get("turret", 0)
    parts = (0.45 * min(1.0, terminals / expected),
             0.15 * min(1.0, twice / max(1, min(expected, terminals or 1))),
             0.25 * min(1.0, cells / float(TARGET_CELLS)),
             0.15 * min(1.0, extras / float(EXTRAS_TARGET)))
    items = [("Terminals", min(terminals, expected), expected),
             ("Gun posts and supplies", min(extras, EXTRAS_TARGET), EXTRAS_TARGET),
             ("Ground covered", min(cells, TARGET_CELLS), TARGET_CELLS)]
    return min(1.0, sum(parts)), items


def modem_wav(seconds=6.0, volume=0.6, rate=16000):
    """An old dial-up modem sound, made up from scratch: dialling tones, a long answer tone, then screeching carrier warbles. Returns the bytes of
    a WAV file (16 bit, mono). Pure maths, nothing recorded."""
    import io
    import random
    import struct
    import wave
    rng = random.Random(9)
    samples = []
    phase = 0.0

    def tone(f1, f2, length, level=1.0):
        nonlocal phase
        for i in range(int(length * rate)):
            t = i / rate
            samples.append(level * 0.5 * (math.sin(2 * math.pi * f1 * t) + (math.sin(2 * math.pi * f2 * t) if f2 else 0.0)))

    def sweep(a, b, length, wobble=0.0, level=1.0):
        nonlocal phase
        n = int(length * rate)
        for i in range(n):
            f = a + (b - a) * i / max(1, n) + wobble * math.sin(i / rate * 31)
            phase += 2 * math.pi * f / rate
            samples.append(level * math.sin(phase))

    def noise(length, level=0.35):
        for _ in range(int(length * rate)):
            samples.append(level * (rng.random() * 2 - 1))

    for pair in ((697, 1209), (770, 1336), (852, 1477), (697, 1336), (941, 1209), (770, 1477)):       # dialling
        tone(pair[0], pair[1], 0.09, 0.8)
        tone(0, 0, 0.05, 0.0)
    tone(0, 0, 0.25, 0.0)
    tone(2100, 0, 0.6, 0.7)                                                                           # answer tone
    tone(0, 0, 0.12, 0.0)
    sweep(1200, 2400, 0.35, 120, 0.8)
    noise(0.12)
    sweep(2400, 1500, 0.3, 200, 0.8)
    tone(980, 1650, 0.25, 0.7)
    noise(0.2)
    while len(samples) < int(seconds * rate):                                                         # the long screech
        sweep(rng.choice((1300, 1800, 2250)), rng.choice((1500, 2000, 2400)), 0.12, 160, 0.75)
        if rng.random() < 0.4:
            noise(0.06, 0.3)
    samples = samples[:int(seconds * rate)]
    fade = int(0.05 * rate)
    for i in range(fade):
        samples[-1 - i] *= i / fade
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s * volume)) * 32000)) for s in samples))
    return out.getvalue()


def blip_wav(frequency=1400, volume=0.5, rate=16000):
    """A short two-note 'got something' chirp."""
    import io
    import struct
    import wave
    samples = []
    for f, length in ((frequency, 0.07), (frequency * 1.5, 0.1)):
        for i in range(int(length * rate)):
            samples.append(math.sin(2 * math.pi * f * i / rate) * (1 - i / (length * rate)))
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"".join(struct.pack("<h", int(s * volume * 32000)) for s in samples))
    return out.getvalue()


VOLUMES = {"Off": 0.0, "Quiet": 0.25, "Normal": 0.5, "Loud": 0.8}


def play(wav_bytes):
    """Plays a WAV from memory without waiting (Windows). Anywhere else, or if it fails, quietly does nothing."""
    try:
        import winsound
        winsound.PlaySound(wav_bytes, winsound.SND_MEMORY | winsound.SND_ASYNC)
    except Exception:
        log.debug("Could not play the hack sound", exc_info=True)


class HackMode:
    def __init__(self, settings, state_provider, settlement_provider, store, maps, narrator, capture=None, sound=None, clock=time.monotonic,
                 known_layouts=None, survey=None, spawn=None):
        self.settings = settings
        self.state_provider = state_provider
        self.settlement_provider = settlement_provider        # () -> {"name", "market", "group", "pads", "map"} or None
        self.store = store
        self.maps = maps
        self.narrator = narrator
        self.capture = capture
        self.sound = sound if sound is not None else play
        self.clock = clock
        self.on_layout = []                                   # called with (map id, market) when a hack settles the layout clearly
        self.known_layouts = known_layouts or {}              # MarketID -> map id (maps/known_settlements.json)
        self.survey = survey or {}                            # MarketID -> {terminals, pictures...} (maps/radar_survey.json, from tester zips)
        self.spawn = spawn or self._thread
        self.on_complete = []                                 # callables(result dict): the lore, mood and next-target parts hang here
        self.active = False
        self.key = None
        self.name = ""
        self.started = 0.0
        self.progress = 0.0
        self.items = []
        self.status = ""
        self.finished_at = None
        self.result = None
        self._told = set()
        self._announced = set()
        self._fails = 0
        self._last_need = 0.0
        self._pictures = 0
        self._stop = threading.Event()
        self._lock = threading.Lock()

    # ---- settings ----
    def enabled(self):
        return bool(self.settings.get("hack.enabled", True))

    def _minutes(self):
        try:
            return max(2.0, min(30.0, float(self.settings.get("hack.minutes", 10))))
        except (TypeError, ValueError):
            return 10.0

    def _volume(self):
        return VOLUMES.get(str(self.settings.get("hack.sound", "Normal")), 0.5)

    # ---- speaking and sound ----
    def say(self, key, fields=None):
        try:
            return self.narrator.say(key, fields or {}) if self.narrator is not None else False
        except Exception:
            log.exception("The hack could not speak")
            return False

    def _play(self, wav_function, *args):
        volume = self._volume()
        if volume <= 0 or self.sound is None:
            return
        try:
            self.sound(wav_function(*args, volume=volume) if args else wav_function(volume=volume))
        except Exception:
            log.debug("The hack sound failed", exc_info=True)

    # ---- is it already mapped? ----
    def mapped_state(self, key):
        """'mine' (you finished it), 'known' (the EOC survey from testers has it) or None."""
        entry = self.store.get(key)
        if entry and entry.get("done"):
            return "mine"
        found = self.survey.get(str(key))
        if found and int(found.get("terminals", 0)) >= MAPPED_MIN_TERMINALS and int(found.get("pictures", 0)) >= MAPPED_MIN_PICTURES:
            return "known"
        return None

    def on_entry(self, entry, silent=False):
        """Journal lines (live only). Stepping out near a base: say whether it is mapped, once per base per session."""
        if silent or not isinstance(entry, dict) or entry.get("event") != "ApproachSettlement" or not self.enabled():
            return
        if not self.settings.get("hack.announce", True) or self.active:
            return
        key = str(entry.get("MarketID") or entry.get("Name") or "")
        if not key or key in self._announced:
            return
        self._announced.add(key)
        state = self.mapped_state(key)
        if state == "mine":
            return
        self.say("Hack_Known" if state == "known" else "Hack_Offer", {"settlement": entry.get("Name") or "this base"})

    # ---- voice ----
    def try_handle(self, text):
        said = clean(text)
        if not said:
            return None
        if _STOP.match(said):
            if self.stop("stop"):
                return "Hack cancelled."
            self.say("Hack_NotRunning")
            return "There is no hack running."
        if _STATUS.match(said):
            return self.status_line()
        if _START.match(said):
            return self.start()
        found = _THIS_IS.match(said)
        if found and self.maps is not None and self.settlement_provider() is not None:
            data = self.maps.find(found.group("what"))
            if data:
                s = self.settlement_provider()
                self.store.describe(s["market"], name=s.get("name"), layout=data["id"])
                self.store.save()
                return "Noted: %s is %s." % (s.get("name") or "this base", data.get("name", data["id"]))
        return None

    def status_line(self):
        if not self.active:
            return "There is no hack running. Say start hack on foot at a base."
        counts = self.store.counts(self.key)
        line = "The hack is at %d percent. I have %d terminals so far." % (round(self.progress * 100), counts.get("terminal", 0))
        need = self._need_text()
        return line + (" " + need if need else "")

    def _need_text(self):
        short = [(label.lower(), needed - found) for label, found, needed in self.items if found < needed]
        if not short:
            return ""
        label, missing = short[0]
        return "I still need more %s." % label if label != "ground covered" else "I still need you to cover more ground."

    # ---- starting and stopping ----
    def start(self):
        if not self.enabled():
            self.say("Hack_Disabled")
            return "The hack game is switched off in the settings."
        if self.active:
            self.say("Hack_AlreadyRunning")
            return "The hack is already running."
        s = self.settlement_provider()
        state = self.state_provider()
        if s is None:
            self.say("Hack_NoSettlement")
            return "There is no base to hack here. Walk up to a settlement on foot first."
        if state is None or not (getattr(state, "status_flags2", 0) & 1) or getattr(state, "latitude", None) is None:
            self.say("Hack_NotOnFoot")
            return "I can only read the radar when you are on foot."
        with self._lock:
            self.active = True
            self.key = str(s["market"])
            self.name = s.get("name") or "this base"
            self.started = self.clock()
            self.progress = 0.0
            self.status = "CONNECTING"
            self.finished_at = None
            self.result = None
            self._told = set()
            self._fails = 0
            self._pictures = 0
            self._last_need = self.clock()
            self._stop.clear()
        self.store.describe(self.key, name=self.name, group=s.get("group"), pads=s.get("pads"), layout=s.get("map"))
        self.items = self._progress()[1]
        self.say("Hack_Start", {"settlement": self.name})
        self._play(modem_wav)
        self.spawn(self._run)
        log.info("Hack started at %s (%s)", self.name, self.key)
        return "Hack started at %s." % self.name

    def stop(self, why="stop"):
        if not self.active:
            return False
        self._stop.set()
        self._finish("aborted" if why == "stop" else why)
        return True

    # ---- the loop ----
    @staticmethod
    def _thread(function):
        threading.Thread(target=function, name="hack", daemon=True).start()

    def _run(self):
        time.sleep(3.0)                                      # let the modem finish
        while self.active and not self._stop.wait(TICK_SECONDS):
            try:
                if not self.tick():
                    break
            except Exception:
                log.exception("The hack stopped because of a problem")
                self._finish("error")
                break

    def _expected_terminals(self):
        s = self.settlement_provider() or {}
        layout = s.get("map") or self.known_layouts.get(self.key) or (self.store.get(self.key) or {}).get("layout")
        data = self.maps.get(layout) if (self.maps is not None and layout) else None
        if data:
            n = len(radar_match.map_terminals(data))
            if n:
                return n
        return EXPECTED_TERMINALS

    def _progress(self):
        counts = self.store.counts(self.key)
        twice = sum(1 for p in self.store.points(self.key, "terminal") if p["n"] >= 2)
        cells = len((self.store.get(self.key) or {}).get("cells", []))
        return progress_of(counts, twice, cells, self._expected_terminals())

    def tick(self):
        """One radar picture. Returns False when the hack is over."""
        if not self.active:
            return False
        now = self.clock()
        s = self.settlement_provider()
        state = self.state_provider()
        if s is None or str(s["market"]) != self.key:
            self._finish("lost")
            return False
        if state is None or not (getattr(state, "status_flags2", 0) & 1):
            self.status = "BACK ON THE SHIP: PAUSED"
            if now - self.started > self._minutes() * 60:
                self._finish("timeout")
                return False
            return True
        picture = self._grab()
        icons = radar_read.find_icons(picture) if picture is not None else None
        if picture is None:
            self._fails += 1
            if self._fails >= FAILS_BEFORE_GIVING_UP:
                self._finish("noradar")
                return False
            return True
        self._fails = 0
        sightings = []
        for icon in icons:
            where = radar_read.to_position(icon, state.latitude, state.longitude, getattr(state, "heading", None), getattr(state, "planet_radius", None))
            if where is not None and icon["kind"] in ("terminal", "ammo", "recharge", "turret"):
                sightings.append((icon["kind"], where[0], where[1]))
        radius = getattr(state, "planet_radius", None)
        if radius:
            added = self.store.add_picture(self.key, sightings, (state.latitude, state.longitude), radius)
            self._pictures += 1
            if added:
                self._play(blip_wav)
        self.progress, self.items = self._progress()
        self.status = "DECRYPTING" if self.progress < 0.5 else "NEARLY THROUGH"
        for mark in MILESTONES:
            if self.progress >= mark and mark not in self._told:
                self._told.add(mark)
                self.say("Hack_Progress_%d" % round(mark * 100), {"percent": round(mark * 100)})
        if now - self._last_need >= NEED_REMINDER_SECONDS and self.progress < 0.9:
            self._last_need = now
            text = self._need_text()
            if text:
                self.say("Hack_Need", {"need": text})
        elapsed = now - self.started
        if self._pictures >= MIN_PICTURES and (self.progress >= 0.98 or (elapsed >= GOOD_ENOUGH_SECONDS and self.progress >= GOOD_ENOUGH)):
            self._finish("complete")
            return False
        if elapsed >= self._minutes() * 60:
            self._finish("timeout")
            return False
        if self._pictures % 5 == 0:
            self.store.save()
        return True

    def _grab(self):
        capture = self.capture
        if capture is None:
            from control.panel_reader import capture_screen as capture
        picture = capture()
        if picture is None:
            return None
        height, width = picture.shape[0], picture.shape[1]
        left, top, right, bottom = radar_read.crop_box(width, height)
        if right - left < 100 or bottom - top < 100:
            return None
        return picture[top:bottom, left:right]

    # ---- the end ----
    def _finish(self, how):
        with self._lock:
            if not self.active:
                return
            self.active = False
        self.status = {"complete": "BASE MAPPED", "timeout": "LINK TIMED OUT", "aborted": "HACK CANCELLED", "lost": "LINK LOST",
                       "noradar": "NO RADAR", "error": "ERROR"}.get(how, how.upper())
        self.finished_at = self.clock()
        self.store.save()
        counts = self.store.counts(self.key)
        result = {"how": how, "key": self.key, "name": self.name, "counts": counts, "progress": self.progress, "pictures": self._pictures,
                  "layout": None, "layout_rows": [], "group": (self.settlement_provider() or {}).get("group") or (self.store.get(self.key) or {}).get("group")}
        log.info("Hack over (%s): %s, %d pictures, %s", how, self.name, self._pictures, counts)
        fields = {"settlement": self.name, "found": counts.get("terminal", 0), "percent": round(self.progress * 100)}
        if how == "complete":
            result["layout"], result["layout_rows"] = self._guess_layout()
            self.store.mark_done(self.key)
            if result["layout"]:
                self.store.describe(self.key, layout=result["layout"])
                for adopt in list(self.on_layout):
                    try:
                        adopt(result["layout"], self.key)            # the map can come up now (settlement_track.adopt_layout)
                    except Exception:
                        log.exception("Could not hand the layout to the map")
            self.store.save()
            self.say("Hack_Complete", fields)
            self._say_layout(result)
        elif how == "timeout":
            self.say("Hack_Timeout", fields)
        elif how == "aborted":
            self.say("Hack_Aborted", fields)
        elif how == "lost":
            self.say("Hack_Lost", fields)
        elif how == "noradar":
            self.say("Hack_NoRadar", fields)
        self.result = result
        if how in ("complete", "timeout"):
            for hook in list(self.on_complete):
                try:
                    hook(result)
                except Exception:
                    log.exception("A hack follow-up failed")

    def _guess_layout(self):
        s = self.settlement_provider() or {}
        known = s.get("map") or self.known_layouts.get(self.key)
        if known:
            return known, []                                  # already certain: the radar only adds to the data
        ids = []
        tracker_ids = s.get("candidate_ids")
        if tracker_ids:
            ids = list(tracker_ids)
        elif s.get("group") and self.maps is not None:
            ids = [i for i, d in self.maps.maps.items() if d.get("group") == s["group"]]
        points = [complex(e, n) for e, n in self.store.terminals_metres(self.key)]
        points.sort(key=lambda p: -p.real)              # a stable order; the matcher uses them all (up to 24)
        if not ids or len(points) < radar_match.MIN_POINTS or self.maps is None:
            return None, []
        return radar_match.suggest(points, self.maps, ids)

    def _say_layout(self, result):
        layout = result.get("layout")
        if layout and self.maps is not None:
            data = self.maps.get(layout) or {}
            self.say("Hack_Layout", {"layout": data.get("name", layout)})
        else:
            self.say("Hack_NoLayout")

    # ---- what the overlay shows ----
    def snapshot(self):
        """What to draw (a plain dict). None when nothing should be shown."""
        if self.active:
            return {"active": True, "title": "EOC LINK", "name": self.name, "status": self.status, "progress": self.progress, "items": list(self.items),
                    "done": False}
        if self.finished_at is not None and self.clock() - self.finished_at < SHOWN_AFTER_SECONDS and self.result:
            return {"active": False, "title": "EOC LINK", "name": self.name, "status": self.status, "progress": self.progress if self.result["how"] != "complete" else 1.0,
                    "items": list(self.items), "done": True, "how": self.result["how"]}
        return None
