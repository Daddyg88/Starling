"""
The MoodEngine: Starling's mood follows what you do in the game.

A hidden score moves a little with each action (see config/mood_rules.json). The numbers below are in "base units";
the score is really `scale` (5) times bigger, so she takes five times longer to reach the top than in 0.41:
    +60 or more   Infatuated    (head over heels)
    +30 .. +60    Close         (very happy, fond of you)
    +10 .. +30    Friendly
    -10 .. +10    Neutral       (calm and professional: where she settles when nothing is happening)
    -35 .. -10    Sarcastic     (annoyed)
    -60 .. -35    Frustrated
    -60 or less   Upset         (really hurt and angry)
Each mood is split into 5 LEVELS (1 = just arrived, 5 = about to move up). Going up a level makes her a little warmer
(or, for the bad moods, going down makes her a little colder): see personality/flavour.py and the Tone_ lines in voicepacks.

It cannot swing wildly, because of four brakes:
    1. SOFT CAP   repeating the same kind of action gives less each time
                  (each repeat counts 60% of the one before; it recovers after ~10 quiet minutes).
    2. HOURLY CAP the score can rise by at most 15 and fall by at most 15 in any hour.
    3. CALMING    the score drifts back toward neutral (1 point per 20 minutes) only while you are really playing.
                  It does NOT drift while Starling is closed or while you are AFK (no game event for 5 minutes),
                  so what you earned is still there when you come back.
    4. HYSTERESIS she only changes mood after passing the line by 4 points, so she never flip-flops.

On top of the score there are MOOD SWINGS (the "swings" list in config/mood_rules.json): a big event (dying, a failed mission, a
heavy trade loss...) puts her in another mood for a few minutes WITHOUT touching the score. When the time is up she says she forgives
you (or calms down after good news) and goes straight back to the mood she was in before. Unsold exploration and biology data is
lost when you die, so dying with a lot of it costs extra points (the "double whammy").

The engine never speaks over safety warnings: she only reacts to ordinary events.
"""

import json
import shutil
import threading
import time
from collections import deque
from datetime import datetime

from core import paths
from core.identity import personalise
from core.logger import get_logger

log = get_logger("mood")

BANDS = ["Upset", "Frustrated", "Sarcastic", "Neutral", "Friendly", "Close", "Infatuated"]
WINDOW_SECONDS = 3600
MAX_OFFLINE_CALMING_SECONDS = 0          # she does NOT calm down while Starling is closed (see offline_calm_hours)
SAVE_AT_MOST_EVERY = 2.0                 # a change is saved straight away, but not more often than this
SAVE_EVERY_SECONDS = 20
ACTIVE_PLAY_SECONDS = 300       # time counts as "playing" for 5 minutes after each game event
SKIP_PREFIXES = ("app.", "journal.", "speech.", "voice.", "personality.")

DEFAULT_SETTINGS = {
    "start_score": 0, "close_at": 30, "friendly_at": 10, "sarcastic_at": -10, "frustrated_at": -35, "infatuated_at": 60, "upset_at": -60,
    "hysteresis": 4, "scale": 5,
    "hourly_cap": 15, "fatigue_factor": 0.6, "recovery_minutes": 10, "calm_minutes_per_point": 20, "offline_calm_hours": 0,
    "react_cooldown_seconds": 90, "react_min_effect": 0.9, "time_together_minutes": 25,
    "combat_grace_seconds": 45, "notoriety_points_per_hour": 6, "notoriety_floor": -25,
    "paint_worn_after_jumps": 150, "paint_points_per_hour": 3, "paint_floor": -20,
}


LEVELS = 5
SCALE_OVERRIDE = None        # the older tests set this to 1 (tests/__init__.py) so they keep using the old -100..100 numbers


def effective_level(settings):
    """Which of her 5 levels inside the mood (1-5): automatic (from the score) or fixed (your dashboard choice)."""
    try:
        if settings.get("personality.mood_mode", "auto") == "fixed":
            value = settings.get("personality.mood_level", 3)
        else:
            value = settings.get("personality.mood_level_live", 3)
        return max(1, min(LEVELS, int(value)))
    except (TypeError, ValueError):
        return 3


# The old (0.41 and earlier) mood lines, -100 .. +100, used to convert a saved score once.
_OLD_EDGES = [-100.0, -60.0, -35.0, -10.0, 10.0, 30.0, 60.0, 100.0]
LEGACY_LANDING = 0.3          # a converted score lands this far (0-1) into its mood, so a maxed-out saved mood starts the climb again


def effective_mood(settings):
    """The mood she is actually in: automatic (from the game) or fixed (your dashboard choice)."""
    if settings.get("personality.mood_mode", "auto") == "fixed":
        return settings.get("personality.mood", "Friendly")
    return settings.get("personality.mood_live", "Friendly")


def load_rules(path=None):
    path = path or (paths.CONFIG_DIR / "mood_rules.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return dict(DEFAULT_SETTINGS), []
    except (OSError, ValueError) as error:
        log.error("Could not read mood_rules.json (%s); mood changes are switched off", error)
        return dict(DEFAULT_SETTINGS), []
    options = dict(DEFAULT_SETTINGS)
    options.update({k: v for k, v in (data.get("settings") or {}).items() if k in DEFAULT_SETTINGS})
    rules = [r for r in data.get("rules", []) if isinstance(r, dict) and r.get("event")]
    return options, rules


def load_swings(path=None):
    """The mood swings from mood_rules.json: [{id, event, when, mood, minutes, forgive, label}, ...]. Bad ones are ignored."""
    path = path or (paths.CONFIG_DIR / "mood_rules.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    swings = []
    for item in data.get("swings", []):
        if isinstance(item, dict) and item.get("event") and item.get("mood") in BANDS:
            try:
                item = dict(item)
                item["minutes"] = max(0.1, min(60.0, float(item.get("minutes", 5))))
            except (TypeError, ValueError):
                continue
            swings.append(item)
    return swings


# ---------------------------------------------------------------------------
# Conditions in the rules file
# ---------------------------------------------------------------------------
def _same(a, b):
    return str(a).lower() == str(b).lower() if isinstance(a, str) or isinstance(b, str) else a == b


def matches(condition, data, ctx):
    """Does `data` satisfy this condition from mood_rules.json? (No condition = always.)"""
    if not condition:
        return True
    if "any" in condition:
        return any(matches(c, data, ctx) for c in condition["any"])
    if "all" in condition:
        return all(matches(c, data, ctx) for c in condition["all"])
    if "ctx" in condition:
        return bool(ctx.get(condition["ctx"]))
    field = condition.get("field")
    if field is None:
        return True
    present = field in data
    if "exists" in condition:
        return present == bool(condition["exists"])
    if not present:
        return False
    value = data[field]
    try:
        if "equals" in condition:
            return _same(value, condition["equals"])
        if "contains" in condition:
            return str(condition["contains"]).lower() in str(value).lower()
        if "is" in condition:
            return value is condition["is"] or value == condition["is"]
        if "gt" in condition:
            return float(value) > float(condition["gt"])
        if "lt" in condition:
            return float(value) < float(condition["lt"])
        if "in" in condition:
            return any(_same(value, v) for v in condition["in"])
    except (TypeError, ValueError):
        return False
    return False


class MoodEngine:
    scale = 1.0                   # set properly in __init__ (class defaults keep objects built without it working)
    max_score = 100.0

    def __init__(self, bus, settings, rules_path=None, save_path=None, dialogue=None, speak=None,
                 clock=time.time, persist=True, wanted_provider=None, scale=None):
        self.bus = bus
        self.settings = settings
        self.options, self.rules = load_rules(rules_path)
        self.swings = load_swings(rules_path)
        self._swing = None                 # {"mood", "until", "forgive", "label"} while she is in a temporary mood
        self._swing_lock = threading.Lock()
        self._unsold = 0                   # exploration / biology work done since the last sale: lost if you die
        self.save_path = save_path or (paths.DATA_DIR / "mood.json")
        self.dialogue = dialogue
        self.speak = speak
        self.clock = clock
        self.persist = persist
        self.good_listener = None          # called with every gain: the favourite-ship counter
        self.wanted_provider = wanted_provider or (lambda: False)   # True while the game says you are wanted

        now = self.clock()
        if scale is None:
            scale = SCALE_OVERRIDE if SCALE_OVERRIDE is not None else self.options["scale"]
        self.scale = max(1.0, float(scale))
        self.max_score = 100.0 * self.scale
        self.score = float(self.options["start_score"])
        self.updated = now
        self._fatigue = {}                 # category -> (value, time)
        self._window = deque()             # (time, applied delta)
        self.band = None
        self.history = deque(maxlen=6)     # (clock time text, label, applied delta) - shown on the Home page
        self._ctx = {"combat_mode": False, "hardpoints": False}
        self._last_attack = None
        self._last_event = None
        self._last_together = now
        self._last_react = None
        self._drain_stamp = now
        self._drain_pending = 0.0
        self.paint_jumps = 0               # jumps since the paintwork was last restored (Elite does not report paint %, so this is an estimate)
        self.paint_debt = 0.0              # mood points lost to worn paint, given back when you repaint
        self._paint_stamp = now
        self._paint_told = False
        self._last_save = 0.0
        self._dirty = False
        self._load()
        self._paint_told = self.paint_worn()      # already worn when we started: don't announce it again
        self.band = self._band_for(self.score, None)
        self._publish_live()

    # ---- wiring ----
    def attach(self):
        self.bus.subscribe("*", self.on_event)

    # ---- reading the mood ----
    @property
    def mood(self):
        return self.band

    def _notoriety_drain(self, now):
        """Being wanted costs points every hour you are actually playing (never while you are away)."""
        stamp, self._drain_stamp = self._drain_stamp, now
        if self._last_event is None or not self.wanted_provider():
            return
        counted = min(now, self._last_event + ACTIVE_PLAY_SECONDS) - stamp
        if counted <= 0:
            return
        floor = float(self.options["notoriety_floor"]) * self.scale
        if self.score <= floor:
            return                                    # annoyed enough; notoriety alone can't push her lower
        points = min(self.score - floor, counted / 3600.0 * float(self.options["notoriety_points_per_hour"]) * self._drain_factor())
        if points <= 0:
            return
        self.score -= points
        self._dirty = True
        self._drain_pending += points
        if self._drain_pending >= 1.0:                # note it on the Home page about once per point
            self.history.appendleft((datetime.fromtimestamp(now).strftime("%H:%M"), "Being wanted (notoriety)", -self._drain_pending))
            self._drain_pending = 0.0
        before = self.band
        self.band = self._band_for(self.score, self.band)
        if self.band != before:
            self._publish_live()
            self._announce_shift()

    def _drain_factor(self):
        """The floors are `scale` times lower now, so the hourly drains are doubled to get there in a sensible time."""
        return max(1.0, self.scale / 2.5)

    def paint_worn(self):
        return self.paint_jumps >= int(self.options["paint_worn_after_jumps"])

    def _paint_drain(self, now):
        """Worn paintwork costs a little every hour you are actually playing, down to a floor. Repainting gives it all back."""
        stamp, self._paint_stamp = self._paint_stamp, now
        if self._last_event is None or not self.paint_worn():
            return
        counted = min(now, self._last_event + ACTIVE_PLAY_SECONDS) - stamp
        if counted <= 0:
            return
        floor = float(self.options["paint_floor"]) * self.scale
        if self.score <= floor:
            return
        points = min(self.score - floor, counted / 3600.0 * float(self.options["paint_points_per_hour"]) * self._drain_factor())
        if points <= 0:
            return
        self.score -= points
        self.paint_debt += points
        self._dirty = True
        before = self.band
        self.band = self._band_for(self.score, self.band)
        if self.band != before:
            self._publish_live()
            self._announce_shift()

    def _paint_jump(self, now):
        was_worn = self.paint_worn()
        self.paint_jumps += 1
        self._dirty = True
        if self.paint_worn() and not was_worn and not self._paint_told and self._can_speak():
            self._paint_told = True
            text = self._line("Paint_Worn", effective_mood(self.settings))
            if text:
                self.history.appendleft((datetime.fromtimestamp(now).strftime("%H:%M"), "Paintwork looks worn (estimated)", 0.0))
                self.speak(text)

    def _repainted(self, data, now):
        item = str((data or {}).get("Item", "")).lower()
        if "paint" not in item and "wear" not in item:
            return
        given_back = self.paint_debt
        self.paint_jumps = 0
        self.paint_debt = 0.0
        self._paint_told = False
        self._paint_stamp = now
        if given_back > 0.05:
            self.score = min(self.max_score, self.score + given_back)     # everything it cost, straight back (no soft cap)
            self.band = self._band_for(self.score, self.band)
            self.history.appendleft((datetime.fromtimestamp(now).strftime("%H:%M"), "Repainted the ship", given_back))
            self._publish_live()
        self._dirty = True
        if self._can_speak():
            text = self._line("Paint_Restored", effective_mood(self.settings))
            if text:
                self.speak(text)

    def refresh(self, now=None):
        """Let time pass: she calms down toward neutral, and her mood band follows."""
        now = self.clock() if now is None else now
        self._notoriety_drain(now)
        self._paint_drain(now)
        self._calm(self._active_seconds(self.updated, now))
        self.updated = now
        self.check_swing(now)
        band = self._band_for(self.score, self.band)
        if band != self.band:
            self.band = band
            self._publish_live()
        else:
            self._publish_level()

    def describe(self):
        self.refresh()
        return "%s %d/%d (%+d)" % (self.band, self.level, LEVELS, round(self.score))

    # ---- saving / loading ----
    def _load(self):
        if not self.persist:
            return
        for path in (self.save_path, self.save_path.with_name(self.save_path.name + ".bak")):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    saved = json.load(handle)
                self.score = self._converted(float(saved.get("score", self.score)), saved.get("scale"))
                self.paint_jumps = max(0, int(saved.get("paint_jumps", 0)))
                self.paint_debt = max(0.0, float(saved.get("paint_debt", 0.0)))
                swing = saved.get("swing")
                if isinstance(swing, dict) and swing.get("mood") in BANDS and float(swing.get("until", 0)) > self.clock():
                    self._swing = {"mood": swing["mood"], "until": float(swing["until"]), "forgive": str(swing.get("forgive", "")),
                                   "label": str(swing.get("label", ""))}
                hours = max(0.0, float(self.options.get("offline_calm_hours", 0) or 0))
                away = max(0.0, min(self.clock() - float(saved.get("saved_at", self.clock())), hours * 3600.0))
                if away:
                    self._calm(away)
                log.info("Loaded her mood from %s: score %.1f", path.name, self.score)
                return
            except FileNotFoundError:
                continue
            except (OSError, ValueError, TypeError) as error:
                log.warning("Could not read the saved mood %s (%s)", path.name, error)
        log.info("No saved mood found; starting at %s", self.score)

    def save(self):
        if not self.persist:
            return
        try:
            self.save_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.save_path.with_suffix(".tmp")
            with open(temp, "w", encoding="utf-8") as handle:
                json.dump({"score": round(self.score, 2), "scale": self.scale, "saved_at": self.clock(),
                           "paint_jumps": self.paint_jumps, "paint_debt": round(self.paint_debt, 2),
                           "swing": self._swing}, handle)
            if self.save_path.exists():
                try:
                    shutil.copyfile(self.save_path, self.save_path.with_name(self.save_path.name + ".bak"))   # last good copy
                except OSError:
                    pass
            temp.replace(self.save_path)
            self._dirty = False
            self._last_save = self.clock()
        except OSError:
            log.warning("Could not save the mood", exc_info=True)

    def _save_soon(self, now):
        """Save a change straight away (so closing the window never loses it), but not more than every 2 seconds."""
        if self.persist and now - self._last_save >= SAVE_AT_MOST_EVERY:
            self.save()

    def reset(self):
        """Back to neutral (the dashboard button)."""
        self.score = float(self.options["start_score"])
        self.paint_debt = 0.0
        self._swing = None
        self._fatigue.clear()
        self._window.clear()
        self.band = self._band_for(self.score, None)
        self._publish_live()
        self.history.clear()
        self.save()

    # ---- the maths ----
    def _active_seconds(self, since, now):
        """Seconds between `since` and `now` that count as really playing. Time while you are AFK (no game event for 5 minutes) never counts."""
        if self._last_event is None:
            return 0.0
        return max(0.0, min(now, self._last_event + ACTIVE_PLAY_SECONDS) - since)

    def _calm(self, seconds):
        """Drift toward neutral (she does not forgive you while you are wanted)."""
        if self.wanted_provider():
            return
        step = seconds / (60.0 * max(1.0, float(self.options["calm_minutes_per_point"])))
        if self.score > 0:
            self.score = max(0.0, self.score - step)
        elif self.score < 0:
            self.score = min(0.0, self.score + step)

    def _fatigue_now(self, category, now):
        value, stamp = self._fatigue.get(category, (0.0, now))
        recovery = 60.0 * max(1.0, float(self.options["recovery_minutes"]))
        return max(0.0, value - (now - stamp) / recovery)

    def _bounds(self):
        o, k = self.options, self.scale
        return [None] + [o[name] * k for name in ("upset_at", "frustrated_at", "sarcastic_at", "friendly_at", "close_at", "infatuated_at")]   # lower edge of each band

    def _converted(self, score, saved_scale):
        """A saved score from an older version (no scale, -100..100) is moved onto the new scale ONCE: she keeps her mood but
        lands near the start of it. A score saved with a scale is just rescaled if the scale changed."""
        if saved_scale is not None:
            try:
                ratio = self.scale / max(1.0, float(saved_scale))
            except (TypeError, ValueError):
                ratio = 1.0
            return max(-self.max_score, min(self.max_score, score * ratio))
        if self.scale == 1.0:
            return max(-100.0, min(100.0, score))
        old = max(-100.0, min(100.0, score))
        new_edges = [-self.max_score] + [b for b in self._bounds()[1:]] + [self.max_score]
        for i in range(len(_OLD_EDGES) - 1):
            if old <= _OLD_EDGES[i + 1] or i == len(_OLD_EDGES) - 2:
                span = _OLD_EDGES[i + 1] - _OLD_EDGES[i]
                share = (old - _OLD_EDGES[i]) / span if span else 0.0
                share = min(1.0, max(0.0, share))
                if i >= 4:                                   # Friendly, Close, Infatuated: land near the start (lowest level)
                    share *= LEGACY_LANDING
                elif i <= 2:                                 # Upset, Frustrated, Sarcastic: the start is the end nearest neutral
                    share = 1.0 - (1.0 - share) * LEGACY_LANDING
                return new_edges[i] + share * (new_edges[i + 1] - new_edges[i])
        return 0.0

    @property
    def level(self):
        """1-5: how far through her current mood she is (1 = just arrived, 5 = nearly the next mood)."""
        return self.level_for(self.score, self.band)

    def level_for(self, score, band=None):
        band = band if band in BANDS else self._band_for(score, None)
        index = BANDS.index(band)
        bounds = self._bounds()
        low = -self.max_score if index == 0 else bounds[index]
        high = self.max_score if index == len(BANDS) - 1 else bounds[index + 1]
        if high <= low:
            return 3
        return max(1, min(LEVELS, 1 + int(LEVELS * (score - low) / (high - low))))

    def _band_for(self, score, current):
        bounds, hys = self._bounds(), float(self.options["hysteresis"])
        if current not in BANDS:
            index = 0
            for i in range(1, len(BANDS)):
                if score >= bounds[i]:
                    index = i
            return BANDS[index]
        index = BANDS.index(current)
        # Going UP happens the moment she reaches the line (33 points means Close at once). The 4 points of hysteresis
        # only apply going DOWN, so a mood does not flicker when she hovers just under it.
        while index < len(BANDS) - 1 and score >= bounds[index + 1]:
            index += 1
        while index > 0 and score < bounds[index] - hys:
            index -= 1
        return BANDS[index]

    def _allowed(self, delta, now):
        """Apply the hourly cap. Returns the part of `delta` that is allowed."""
        while self._window and now - self._window[0][0] > WINDOW_SECONDS:
            self._window.popleft()
        cap = float(self.options["hourly_cap"])
        if delta > 0:
            used = sum(d for _t, d in self._window if d > 0)
            return max(0.0, min(delta, cap - used))
        used = -sum(d for _t, d in self._window if d < 0)
        return -max(0.0, min(-delta, cap - used))

    SWING_LEVEL = 3

    def _shown_band(self):
        """The mood she shows: her temporary swing if she has one, else the real mood from the score."""
        swing = self._swing
        return swing["mood"] if swing else self.band

    def _shown_level(self):
        return self.SWING_LEVEL if self._swing else self.level

    def swing_active(self):
        return self._swing is not None

    def _start_swing(self, swing, now):
        mood = swing["mood"]
        until = now + 60.0 * swing["minutes"]
        with self._swing_lock:
            current = self._swing
            if current and BANDS.index(current["mood"]) < BANDS.index(mood) <= BANDS.index("Neutral") and current["until"] > now:
                current["until"] = max(current["until"], until)          # already in a worse mood: only stay in it longer
            else:
                self._swing = {"mood": mood, "until": until, "forgive": swing.get("forgive", ""), "label": swing.get("label", swing.get("id", ""))}
        self.history.appendleft((datetime.fromtimestamp(now).strftime("%H:%M"), "Mood swing: %s for %g min (%s)" % (
            mood, swing["minutes"], swing.get("label", swing.get("id", ""))), 0.0))
        self._dirty = True
        self._publish_live()
        log.info("Mood swing: %s for %g minutes (%s)", mood, swing["minutes"], swing.get("id"))

    def check_swing(self, now=None):
        """Ends her temporary mood when its time is up: she says the forgiving line and returns to her real mood. Safe to call often."""
        now = self.clock() if now is None else now
        with self._swing_lock:
            swing = self._swing
            if swing is None or now < swing["until"]:
                return False
            self._swing = None
        self._dirty = True
        self._publish_live()
        log.info("Mood swing over (%s); back to %s", swing["label"], self.band)
        if swing["forgive"] and self._can_speak():
            text = self._line(swing["forgive"], effective_mood(self.settings))
            if text:
                self.speak(text)
        return True

    def start_timer(self, seconds=5.0):
        """A small background tick so a swing ends on time even when nothing is happening in the game."""
        if getattr(self, "_timer_thread", None) is not None:
            return

        def loop():
            while not self._timer_stop.wait(seconds):
                try:
                    self.check_swing()
                except Exception:
                    log.exception("Mood swing timer problem")
        self._timer_stop = threading.Event()
        self._timer_thread = threading.Thread(target=loop, name="mood-swing", daemon=True)
        self._timer_thread.start()

    def stop_timer(self):
        if getattr(self, "_timer_thread", None) is not None:
            self._timer_stop.set()
            self._timer_thread = None

    def _publish_level(self):
        """The level can change without the mood changing: keep the published number up to date."""
        try:
            level = self._shown_level()
            if self.settings.get("personality.mood_level_live") != level:
                self.settings.set("personality.mood_level_live", level)
        except Exception:
            log.debug("Could not publish the mood level", exc_info=True)

    def _publish_live(self):
        try:
            self.settings.set("personality.mood_live", self._shown_band())
            self.settings.set("personality.mood_level_live", self._shown_level())
        except Exception:
            log.debug("Could not publish the live mood", exc_info=True)

    # ---- hearing about the game ----
    def on_event(self, event):
        name = event.name
        if name.startswith(SKIP_PREFIXES):
            return
        try:
            self._handle(event)
        except Exception:
            log.exception("Mood engine problem with %s", name)   # a mood bug must never hurt anything else

    def _handle(self, event):
        now = self.clock()
        name, data = event.name, event.data or {}
        self._track_context(name, data, now)
        self._maybe_time_together(now)
        self.refresh(now)                 # calming and notoriety use the time since the previous event
        self._last_event = now
        if name == "FSDJump":
            self._paint_jump(now)
        elif name == "Repair":
            self._repainted(data, now)
        self._enrich(name, data)
        for rule in self.rules:
            if rule["event"] != name:
                continue
            if not matches(rule.get("when"), data, self._ctx_flags(now)):
                continue
            self._apply(rule, event, now)
            break                                    # only the first matching rule counts
        if name == "Died":
            self._lose_data(now)
        for swing in self.swings:
            if swing["event"] == name and matches(swing.get("when"), data, self._ctx_flags(now)):
                self._start_swing(swing, now)
                break
        if self._dirty and now - self._last_save >= SAVE_EVERY_SECONDS:
            self.save()

    def _enrich(self, name, data):
        """Adds worked-out fields to the event's data so the rules file can use them (the journal does not give them)."""
        if name == "MarketSell":
            try:
                paid = float(data["AvgPricePaid"]) * float(data.get("Count", 0))
                data["Loss"] = max(0.0, paid - float(data.get("TotalSale", 0)))      # what you lost on this sale
            except (KeyError, TypeError, ValueError):
                pass

    # unsold work worth this many "units" each (exploration data and biology samples are lost when you die)
    UNSOLD_UNITS = {"Scan": 1, "FSSAllBodiesFound": 2, "SAAScanComplete": 2, "CodexEntry": 1}

    def _lose_data(self, now):
        """Dying loses everything you have not sold yet: a second penalty on top of the death itself."""
        units, self._unsold = self._unsold, 0
        if units <= 0:
            return
        rule = next((r for r in self.rules if r["event"] == "_data_lost"), None)
        if rule is None:
            return
        fake = type("Lost", (), {"name": "_data_lost", "data": {"Units": units}, "priority": "normal"})()
        self._last_react = None                 # this one is its own sentence, not part of the death reaction
        self._apply(rule, fake, now)

    def _track_context(self, name, data, now):
        if name in self.UNSOLD_UNITS:
            self._unsold += self.UNSOLD_UNITS[name]
        elif name == "ScanOrganic" and str(data.get("ScanType", "")).lower() == "analyse":
            self._unsold += 5
        elif name in ("SellExplorationData", "MultiSellExplorationData", "SellOrganicData"):
            self._unsold = 0
        if name == "CombatModeOn":
            self._ctx["combat_mode"] = True
        elif name == "AnalysisModeOn":
            self._ctx["combat_mode"] = False
        elif name == "HardpointsDeployed":
            self._ctx["hardpoints"] = True
        elif name == "HardpointsRetracted":
            self._ctx["hardpoints"] = False
        elif name in ("UnderAttack", "Interdicted", "FactionKillBond", "Bounty", "PVPKill", "CapShipBond"):
            self._last_attack = now

    def _ctx_flags(self, now):
        recent = self._last_attack is not None and now - self._last_attack < float(self.options["combat_grace_seconds"])
        in_combat = self._ctx["combat_mode"] or self._ctx["hardpoints"] or recent
        return {"in_combat": in_combat, "not_in_combat": not in_combat}

    def _maybe_time_together(self, now):
        """A small thank-you for time spent flying together (only while you are actively playing)."""
        gap = 60.0 * float(self.options["time_together_minutes"])
        if now - self._last_together < gap:
            return
        active = self._last_event is not None and now - self._last_event < 300 and not self.wanted_provider()
        self._last_together = now
        if active:
            for rule in self.rules:
                if rule["event"] == "_time_together":
                    self._apply(rule, None, now)
                    break

    def _base_delta(self, rule, data):
        if "tiers" in rule:
            try:
                amount = float(data.get(rule.get("amount_field", ""), 0))
            except (TypeError, ValueError):
                return 0.0
            points = 0.0
            for minimum, value in rule["tiers"]:
                if amount >= minimum:
                    points = float(value)
            return points
        return float(rule.get("delta", 0))

    def _apply(self, rule, event, now):
        data = (event.data if event is not None else {}) or {}
        base = self._base_delta(rule, data)
        if base == 0:
            return
        category = rule.get("category") or rule.get("id") or "other"
        fatigue = self._fatigue_now(category, now)
        effective = base * (float(self.options["fatigue_factor"]) ** fatigue)    # the soft cap
        self._fatigue[category] = (fatigue + 1.0, now)
        self.refresh(now)
        applied = self._allowed(effective, now)                                  # the hourly cap
        if abs(applied) < 0.05:
            return
        self._window.append((now, applied))
        if applied > 0 and self.good_listener is not None:
            try:
                self.good_listener(applied)
            except Exception:
                log.exception("The favourite ship counter failed")
        before = self.band
        self.score = max(-self.max_score, min(self.max_score, self.score + applied))
        self.band = self._band_for(self.score, self.band)
        self._dirty = True
        self._save_soon(now)
        self.history.appendleft((datetime.fromtimestamp(now).strftime("%H:%M"), rule.get("label", rule.get("id", "")), applied))
        log.debug("Mood %+.2f (%s) -> %.1f %s", applied, rule.get("id"), self.score, self.band)
        if self.band != before:
            self._publish_live()
            self._announce_shift()
        else:
            self._publish_level()
            if event is not None:
                self._react(rule, event, applied, now)

    # ---- speaking about it ----
    def _can_speak(self):
        return (self.speak is not None and self.dialogue is not None
                and self.settings.get("speech.enabled", True)
                and self.settings.get("personality.style", "personality") == "personality")

    def _line(self, key, mood=""):
        allow = bool(self.settings.get("speech.allow_mature", False))
        line = self.dialogue.pick(key, mood, allow, False)
        return personalise(line.text, self.settings) if line is not None else None

    def _react(self, rule, event, applied, now):
        key = rule.get("react")
        if not key or not self._can_speak() or event.priority == "critical":
            return
        if abs(applied) < float(self.options["react_min_effect"]):
            return                                        # she has stopped fussing about this one
        if self._last_react is not None and now - self._last_react < float(self.options["react_cooldown_seconds"]):
            return
        text = self._line(key, effective_mood(self.settings))
        if text:
            self._last_react = now
            self.speak(text)

    def _announce_shift(self):
        if not self._can_speak():
            return
        text = self._line("MoodShift_" + self.band)
        if text:
            self._last_react = self.clock()
            self.speak(text)
