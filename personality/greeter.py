"""
The login greeting: when you load into the game she says hello, which ship you are in,
where you are (system, docked at a station, or landed on a planet) and how she feels about you.

    "Welcome back, Commander. You're flying the Python called Stardust.
     We're docked at Jameson Memorial in the Shinrarta Dezhra system. ||
     I'm still not very happy with you, by the way."

The game writes LoadGame first and Location a moment later. The greeting waits for Location
(or 8 seconds, whichever comes first) so it knows where you are.
In "info" style she just states the facts - no mood, no pet names.
"""

import random
import threading
import time

from core.identity import personalise
from core.ships import ship_name
from core.logger import get_logger
from personality.mood_engine import effective_mood

log = get_logger("greeter")

WAIT_FOR_LOCATION_SECONDS = 8.0
MIN_GAP_SECONDS = 60.0
DEFAULTS = {"Ship": "ship", "System": "this system"}


class _Safe(dict):
    def __missing__(self, key):
        return "?"


class LoginGreeter:
    def __init__(self, bus, speech, dialogue, settings, state_provider=None, flavour=None,
                 clock=time.monotonic, timer_factory=None, memory=None, mood=None):
        self.bus = bus
        self.speech = speech
        self.dialogue = dialogue
        self.settings = settings
        self.state_provider = state_provider or (lambda: None)
        self.flavour = flavour
        self.memory = memory            # memory/recall.py (optional)
        self.mood = mood                # the MoodEngine (optional): knows if she is in a temporary mood
        self.clock = clock
        self.timer_factory = timer_factory or (lambda seconds, function: threading.Timer(seconds, function))
        self._pending = None          # LoadGame data waiting for its Location
        self._timer = None
        self._lock = threading.Lock()
        self._last_greeting = None

    def attach(self):
        self.bus.subscribe("LoadGame", self.on_load_game)
        self.bus.subscribe("Location", self.on_location)

    # ---- hearing about the game ----
    def enabled(self):
        return bool(self.settings.get("personality.login_greeting", True)) and self.settings.get("speech.enabled", True)

    def on_load_game(self, event):
        if not self.enabled():
            return
        now = self.clock()
        if self._last_greeting is not None and now - self._last_greeting < MIN_GAP_SECONDS:
            return
        with self._lock:
            self._pending = dict(event.data or {})
            if self._timer is not None:
                self._timer.cancel()
            self._timer = self.timer_factory(WAIT_FOR_LOCATION_SECONDS, self._timeout)
            try:
                self._timer.daemon = True
            except AttributeError:
                pass
            self._timer.start()

    def on_location(self, event):
        with self._lock:
            if self._pending is None:
                return
            load, self._pending = self._pending, None
            if self._timer is not None:
                self._timer.cancel()
        self._greet(load, dict(event.data or {}))

    def _timeout(self):
        with self._lock:
            if self._pending is None:
                return
            load, self._pending = self._pending, None
        self._greet(load, None)

    # ---- saying it ----
    def _greet(self, load, location):
        try:
            text = self.compose(load, location)
            if text:
                self._last_greeting = self.clock()
                self.speech.say(text=text, priority="normal", event_name="login.greeting")
        except Exception:
            log.exception("Could not make the login greeting")

    def _pick(self, key, mood):
        allow = bool(self.settings.get("speech.allow_mature", False))
        line = self.dialogue.pick(key, mood, allow, False)
        return line.text if line is not None else None

    def _say(self, key, mood, values):
        text = self._pick(key, mood)
        if not text:
            return None
        return personalise(text.format_map(_Safe(values)), self.settings)

    def compose(self, load, location):
        """Build the greeting text from the LoadGame and Location data. Pure: easy to test."""
        state = self.state_provider()
        personality = self.settings.get("personality.style", "personality") == "personality"
        mood = effective_mood(self.settings) if personality else ""

        ship = ship_name(load.get("Ship") or getattr(state, "ship", None), load.get("Ship_Localised")) or DEFAULTS["Ship"]
        name = load.get("ShipName") or getattr(state, "ship_name", None) or ""
        values = {"ship": ship + (" called %s" % name if name and name.lower() != ship.lower() else "")}

        parts = []
        opener = self._say("Login_Open", mood, values)
        if opener and self.flavour is not None and personality:
            opener = self.flavour.rename(opener)
        parts.append(opener)
        is_favourite = bool(getattr(state, "favourite_ship", None)) and str(getattr(state, "ship", "") or "").lower() == state.favourite_ship
        parts.append((self._say("Login_Ship_Favourite", mood, values) if is_favourite else None) or self._say("Login_Ship", mood, values))

        where = self._where(location, state, mood, values)
        parts.append(where)
        if location and location.get("Wanted"):
            parts.append(self._say("Login_Wanted", mood, values))

        sentence = " ".join(p for p in parts if p)
        if self.memory is not None and personality:
            try:
                remembered = self.memory.login_line()
            except Exception:
                log.exception("Could not recall a memory for the greeting")
                remembered = None
            if remembered:
                sentence = "%s || %s" % (sentence, remembered)
        if personality:
            key = "Login_Mood_" + (mood or "Friendly")
            if (self.flavour is not None and self.flavour.innuendo_on(mood) and mood not in ("Sarcastic", "Frustrated", "Upset")
                    and random.random() < 0.5):
                key = "Login_Mood_Innuendo"
            still = self._swing_line(values)
            feeling = still or self._say(key, "", values) or self._say("Login_Mood_" + (mood or "Friendly"), "", values)
            if feeling:
                sentence = "%s || %s" % (sentence, feeling)
        return sentence.strip()

    def _swing_line(self, values):
        """While she is still in a temporary mood (she was upset with you for dying), she says so instead of the usual feeling."""
        try:
            key = self.mood.swing_still_key() if self.mood is not None else ""
        except Exception:
            return None
        return self._say(key, effective_mood(self.settings), values) if key else None

    def _where(self, location, state, mood, values):
        if location is not None:
            system = location.get("StarSystem") or getattr(state, "system", None)
            station = location.get("StationName")
            body = location.get("Body")
            docked, landed = bool(location.get("Docked")), bool(location.get("Landed"))
        else:                                            # no Location arrived: use what we already know
            system = getattr(state, "system", None)
            station = getattr(state, "station", None)
            body = None
            docked, landed = bool(getattr(state, "docked", False)), False
        if not system:
            return None
        values.update({"system": system, "station": station or "the station", "body": body or "a planet"})
        if docked and station:
            return self._say("Login_Docked", mood, values)
        if landed:
            return self._say("Login_Landed", mood, values)
        return self._say("Login_Space", mood, values)
