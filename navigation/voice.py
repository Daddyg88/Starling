"""
Voice control for the neutron plotter.

    "Plot a neutron route to Colonia"           works out the route and puts the first waypoint on your clipboard
    "Plot a neutron route to my destination"    uses the Destination box on the Navigation page
    "Where's the next waypoint?"                says it again and copies it again
    "How far is left?"                          jumps and neutron stops remaining
    "Replot the route"                          new route from where you are now, same destination
    "Cancel the route"

Destinations: a short list of famous ones is built in (and you can add your own in settings.json under
neutron.favourites), because a microphone is bad at "Sagittarius A star". Anything else is looked up on Spansh,
and she tells you the name she found so you can cancel if it is wrong.
"""

import json
import re
import threading
import time

from core import paths
from core.identity import personalise
from core.logger import get_logger
from navigation.edastro import EdAstro, EdAstroError, distance
from navigation.engineers import EngineerBook, distance as engineer_distance
from navigation.spansh import SpanshError
from personality.mood_engine import effective_mood

log = get_logger("route.voice")

FAVOURITES = {
    "colonia": "Colonia",
    "sol": "Sol",
    "the bubble": "Sol",
    "earth": "Sol",
    "sagittarius a": "Sagittarius A*",
    "sagittarius a star": "Sagittarius A*",
    "sag a": "Sagittarius A*",
    "the galactic centre": "Sagittarius A*",
    "the galactic center": "Sagittarius A*",
    "galactic centre": "Sagittarius A*",
    "galactic center": "Sagittarius A*",
    "beagle point": "Beagle Point",
    "jaques": "Colonia",
}

_FILLER = re.compile(r"\b(please|starling|commander|cmdr|could you|can you|would you|will you|for me|hey|ok|okay|now|just|quickly)\b")
_PLOT = re.compile(r"\b(plot|set|work out|find|calculate|create|make|give me|get me|map out|lay in|plan|chart)\b"
                   r".*?\b(neutron|route|course|highway|trail)\b.*?\bto\b\s+(?P<dest>.+)$")
# "plot a neutron route" with no place named: use the destination set in the game
_PLOT_BARE = re.compile(r"^(?:\w+ ){0,3}?(plot|set|work out|find|calculate|create|make|give me|get me|map out|lay in|plan|chart|start|use|run|do)\b"
                        r".*\bneutron\b.*\b(route|course|highway|trail|plotter|plot)\b(?!.*\bto\b)|^neutron (route|course|plotter|plot|highway)$|^(plot|start) neutron$")
# "emergency protocol": Spansh does not know where I am, find a known landmark nearby and get me there
_EMERGENCY = re.compile(r"\b(emergency (protocol|route|plot|plotter)|(i m|i am|we re|we are) lost|spansh (can t|cannot|doesn t) find me|"
                        r"find (me )?(a |the )?nearest (landmark|poi|point of interest|beacon|nav marker|carrier)|get me out of here)\b")
_NEXT = re.compile(r"\b(next (waypoint|stop|neutron|neutron star|star)|where (to )?next|where s the next|waypoint again|repeat the waypoint)\b")
_STATUS = re.compile(r"\b(how far|how much (further|farther|left)|how many (jumps|stops|neutron).*left|route status|how s the route|jumps left|stops left)\b")
_CANCEL = re.compile(r"\b(cancel|clear|stop|abandon|forget|scrap|delete|drop|reset|remove)\b.*\b(neutron route|the route|my route|route|root|course|plot|neutron plotter|emergency)\b")
_REPLOT = re.compile(r"\b(re ?plot|plot (it )?again|redo the route|new route from here|recalculate)\b")
# "plot the next waypoint" is the hands-free galaxy map macro (control/catalog.py), not a question about the route
_PLOT_NEXT = re.compile(r"\b(plot|set|put in|enter|load|lay in|select)\b.*\b(next|waypoint)\b|\bnext waypoint in\b")
# "take us to my carrier" / "set a course for the squad carrier": no word like route needed
_CARRIER_GO = re.compile(r"\b(plot|set|lay in|navigate|take (me|us)|head|fly|go|route|course)\b.*\b(to|for)\b (?P<dest>(?:(?:my|the|our) )?"
                         r"(?:(?:squad|squadron|wing) (?:fleet )?carrier|(?:fleet |home )?carrier))$")
# "take me to Felicity Farseer": only counts when the name really is an engineer (navigation/engineers.py)
_GO_ENGINEER = re.compile(r"^(?:\w+ ){0,2}?(?:take|bring|fly|get|navigate|head|go|plot|set|lay in|route|lead|find)\b.*?\b(?:to|for|towards?)\b\s+(?P<who>.+)$")
_WHERE_ENGINEER = re.compile(r"^where (?:is|s|does) (?P<who>.+?)(?: live| based| located)?$")
_TAIL = re.compile(r"\b(using|via|by|with|through)\b.*\bneutron.*$|\bneutron (route|stars?)\b$")


_NEUTRON_WORD = re.compile(r"\b(neutrons?|neutral|neatron|neotron|newtron|nutron|nuetron|neutrino|new tron|new trunk|neutro)\b")
_MISHEARD = (
    (re.compile(r"\b(platter|plotta|plota|plodder|plot her|plot are)\b"), "plotter"),
    (re.compile(r"\b(root|rout|rote|route s)\b"), "route"),
    (re.compile(r"\b(cores|coarse|cors|chorus|horse|course s)\b"), "course"),
    (re.compile(r"^(touch|blot|plod|plots|plat|lot|clot|pilot|plant|flat|plug|plop) "), "plot "),
    (re.compile(r"\byour neutron\b"), "a neutron"),
)


def fix_neutron_mishearings(said):
    """The microphone often hears 'neutron' as neutral, platter, cores, root... Fix those, but only in a sentence about neutrons."""
    if not _NEUTRON_WORD.search(said):
        return said
    said = _NEUTRON_WORD.sub("neutron", said)
    for pattern, replacement in _MISHEARD:
        said = pattern.sub(replacement, said)
    return " ".join(said.split())


def clean(text):
    text = re.sub(r"[^a-z0-9*\s]", " ", str(text or "").lower().replace("*", " star "))
    text = _FILLER.sub(" ", text)
    return " ".join(text.split())


_NUMBER_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
                 "nine": "9", "ten": "10", "won": "1", "to": "2", "too": "2", "for": "4", "tin": "10"}
_SLOT = re.compile(r"^(?:my |the |our )?(?:(?P<squad>(?:squad|squadron|wing) (?:fleet )?carrier)|(?P<fleet>(?:(?:fleet|home) )?carrier)|(?P<home>home(?: system| base| star)?)|book ?mark(?: number| no)? (?P<n>\w+))$")
_SAVE = re.compile(r"\b(save|store|remember|bookmark|mark|set|put|keep|file)\b (?:this|the current|current|our current|my current|here)?\s*"
                   r"(?:system|location|place|star|here)?\s*\b(as|in|into|to|under|for)\b\s+(?P<slot>.+)$")
_SAVE_SLOT_FIRST = re.compile(r"\b(set|make)\b (?P<slot>.+?) (?:to|as|equal to) (?:here|this system|the current system|where we are|where i am)$")


def slot_key(text):
    """'home' -> 'home', 'bookmark three' -> 'b3', anything else -> None."""
    found = _SLOT.match(clean(text))
    if not found:
        return None
    if found.group("squad"):
        return "squad"
    if found.group("fleet"):
        return "fleet"
    if found.group("home"):
        return "home"
    number = _NUMBER_WORDS.get(found.group("n"), found.group("n"))
    return "b%s" % number if number.isdigit() and 1 <= int(number) <= 10 else None


def slot_name(key):
    return {"home": "Home", "fleet": "Fleet carrier", "squad": "Squad carrier"}.get(key) or "Bookmark %s" % key[1:]


class Narrator:
    """Says route lines in her current mood (voicepacks/default/route.json). Plain facts are always in the line."""

    def __init__(self, speech_provider, dialogue, settings):
        self.speech_provider = speech_provider
        self.dialogue = dialogue
        self.settings = settings

    def say(self, key, fields=None):
        speech = self.speech_provider()
        dialogue = self.dialogue() if callable(self.dialogue) else self.dialogue
        if speech is None or not self.settings.get("speech.enabled", True) or dialogue is None:
            return False
        info = self.settings.get("personality.style", "personality") == "info"
        mood = "" if info else effective_mood(self.settings)
        line = dialogue.pick(key, mood, bool(self.settings.get("speech.allow_mature", False)), False)
        if line is None:
            return False
        text = line.text
        try:
            text = text.format_map(_Quiet(fields or {}))
        except (ValueError, IndexError):
            pass
        return bool(speech.say(text=personalise(text, self.settings), priority="normal", event_name="personality.route"))


class _Quiet(dict):
    def __missing__(self, key):
        return ""


def is_caspian(state):
    """True when the ship you are flying is the Caspian Explorer (journal name explorer_nx)."""
    for text in (getattr(state, "ship", None), getattr(state, "ship_model", None)):
        low = str(text or "").lower()
        if low == "explorer_nx" or "caspian" in low:
            return True
    return False


class RouteVoice:
    def __init__(self, follower, spansh, narrator, settings, state_provider, spawn=None):
        self.follower = follower
        self.spansh = spansh
        self.narrator = narrator
        self.settings = settings
        self.state_provider = state_provider
        self.spawn = spawn or self._thread
        self._busy = False
        self.target_override = None
        self.sleep = time.sleep
        self.clock = time.monotonic
        self._ignore_until = 0.0         # her own galaxy map macro sets targets too: ignore those
        self._last_auto = ""
        self._home_said = None
        self.edastro = EdAstro()
        self.emergency_file = paths.DATA_DIR / "emergency_route.json"
        self._emergency = self._load_emergency()
        self.engineers = EngineerBook()
        self.plot_macro = None           # the app sets this: plots a system with the galaxy map macro (the "auto plotter"): (system) -> (ok, reason)
        self.game_target = None          # the app sets this: a function giving the destination picked in the game's galaxy map

    # ---- "plot it for me when I set a target in the galaxy map" ----
    def on_nav_route(self, _event=None):
        """The game says a route was set (or cleared). Wait a moment for NavRoute.json, then plot a neutron route to its end."""
        if not self.enabled() or not self.settings.get("neutron.auto_on_target", False):
            return
        if self.clock() < self._ignore_until:
            return
        self.spawn(self._auto_plot_target)

    def _auto_plot_target(self):
        self.sleep(1.5)
        if self.clock() < self._ignore_until or self._busy:
            return
        name = self._target_in_game()
        state = self.state_provider()
        here = str(getattr(state, "system", "") or "")
        if not name or name.casefold() == here.casefold() or name.casefold() == self._last_auto.casefold():
            return
        follower = self.follower
        if follower.active and (name.casefold() == str(follower.destination).casefold()
                                or any(w["system"].casefold() == name.casefold() for w in follower.waypoints)):
            return                          # that is part of the route she is already following
        self._last_auto = name
        self.plot(name)

    def _target_in_game(self):
        try:
            name = str(self.game_target() or "").strip() if self.game_target else ""
            log.info("The destination set in the game's galaxy map: %s", name or "(none: no plotted course and no target set)")
            return name
        except Exception:
            log.exception("Could not read the game's route")
            return ""

    def supercharge(self):
        """x6 in the Caspian Explorer (the only ship that gets it), otherwise whatever the dashboard says."""
        if self.settings.get("neutron.auto_x6", True) and is_caspian(self.state_provider()):
            return 6
        return self.settings.get("neutron.supercharge", 4)

    @staticmethod
    def _thread(function):
        threading.Thread(target=function, name="plot-route", daemon=True).start()

    def enabled(self):
        return bool(self.settings.get("neutron.enabled", True))

    # ---- what was said? returns a sentence for the log, or None if this wasn't about routes ----
    def try_handle(self, text):
        if not self.enabled():
            return None
        said = fix_neutron_mishearings(clean(text))
        if not said:
            return None
        if _PLOT_NEXT.search(said):
            return None
        saved = self._save_bookmark(said)
        if saved is not None:
            return saved
        engineer = self._engineer_asked(said)
        if engineer is not None:
            return engineer
        found = _CARRIER_GO.search(said)
        if found:
            return self.plot(found.group("dest"))
        found = _PLOT.search(said)
        if found:
            return self.plot(found.group("dest"))
        if _PLOT_BARE.search(said) and not _PLOT_NEXT.search(said):
            return self.plot("my target")
        if _EMERGENCY.search(said):
            return self.start_emergency()
        if _REPLOT.search(said):
            return self.plot(self.follower.destination or str(self.settings.get("neutron.destination", "")))
        if _CANCEL.search(said) and (self.follower.active or self._emergency or re.search(r"\b(route|root|course|emergency)\b", said)):
            had = self.follower.active or bool(self._emergency)
            self.follower.clear()
            self._set_emergency(None)
            self.target_override = None
            self.narrator.say("RouteCancelled" if had else "RouteNone")
            return "Route cancelled." if had else "There was no route."
        if _NEXT.search(said) and (self.follower.active or "waypoint" in said or "route" in said):
            return self.next_waypoint()
        if _STATUS.search(said) and ("route" in said or self.follower.active):
            return self.status()
        return None

    def _save_bookmark(self, said):
        """'Save this system as bookmark 3' / 'set home to here'. Returns a sentence, or None if it wasn't that."""
        found = _SAVE_SLOT_FIRST.search(said) or _SAVE.search(said)
        key = slot_key(found.group("slot")) if found else None
        if key is None:
            return None
        state = self.state_provider()
        here = getattr(state, "system", None) if state is not None else None
        if not here:
            self.narrator.say("RouteNoLocation")
            return "I don't know where we are yet."
        self.settings.set("bookmarks." + key, here)
        try:
            self.settings.save()
        except OSError:
            log.exception("Could not save the bookmark")
        self.narrator.say("RouteBookmarkSaved", {"slot": slot_name(key), "system": here})
        return "Saved %s as %s" % (here, slot_name(key))

    def set_target(self, system_name):
        """The next run of the galaxy map macro pastes THIS system (copied to the clipboard) instead of the next waypoint.
        Used when she finds a place to sell: no route is worked out, only the macro runs."""
        self.target_override = str(system_name or "").strip() or None

    def prepare_plot(self):
        """Runs just before the 'plot the next waypoint' macro: is there something to paste?"""
        self._ignore_until = self.clock() + 90          # the macro sets a target in the game itself: not a new request
        if self.target_override:
            name, self.target_override = self.target_override, None
            if self.follower.copier(name):
                return True, ""
            return False, "I couldn't copy %s to your clipboard." % name
        if not self.follower.active:
            self.narrator.say("RouteNone")
            return False, "There is no route plotted."
        if not self.settings.get("neutron.clipboard", True):
            return False, "Switch on 'Copy the next waypoint to my clipboard' so I have something to paste."
        if not self.follower.copy_next():
            return False, "I couldn't copy the waypoint to your clipboard."
        return True, ""

    def next_waypoint(self):
        if not self.follower.active:
            self.narrator.say("RouteNone")
            return "No route plotted."
        self.follower.copy_next()
        self.narrator.say("RouteNextAgain", self.follower.fields())
        return "Next waypoint: %s" % self.follower.next_waypoint()["system"]

    def status(self):
        if not self.follower.active:
            self.narrator.say("RouteNone")
            return "No route plotted."
        self.narrator.say("RouteStatus", self.follower.fields())
        return "%d jumps left" % self.follower.total_jumps_left()

    # ---- plotting (on its own thread: Spansh can take a while) ----
    def plot(self, destination_text):
        spoken = _TAIL.sub("", clean(destination_text)).strip()
        key = None if spoken in self._my_favourites() else slot_key(spoken)
        if key in ("fleet", "squad"):
            return self._plot_carrier(key)
        if key is not None and not str(self.settings.get("bookmarks." + key, "") or "").strip():
            self.narrator.say("RouteBookmarkEmpty", {"slot": slot_name(key)})
            return "%s is empty." % slot_name(key)
        name = self._destination_name(destination_text)
        if not name:
            self.narrator.say("RouteNoDestination")
            return "No destination."
        if self._busy:
            return "Already plotting."
        self._busy = True
        self.narrator.say("RoutePlotting", {"destination": name})
        self.spawn(lambda: self._plot_now(name))
        return "Plotting a neutron route to %s" % name

    # ---- "take me to Felicity Farseer" ----
    def _engineer_asked(self, said):
        found = _GO_ENGINEER.search(said)
        if found:
            engineer = self.engineers.find(found.group("who"))
            if engineer is not None:
                return self.go_to_engineer(engineer)
        found = _WHERE_ENGINEER.search(said)
        if found:
            engineer = self.engineers.find(found.group("who"))
            if engineer is not None:
                return self.where_is_engineer(engineer)
        return None

    def _engineer_fields(self, engineer):
        state = self.state_provider()
        miles = engineer_distance(getattr(state, "star_pos", None), engineer.pos)
        return {"engineer": engineer.spoken(), "system": engineer.system, "station": engineer.station,
                "distance": "{:,}".format(int(round(miles))) if miles is not None else "an unknown number of", "ly": miles}

    def where_is_engineer(self, engineer):
        fields = self._engineer_fields(engineer)
        self.narrator.say("EngineerWhere", fields)
        return "%s is at %s in %s" % (engineer.name, engineer.station, engineer.system)

    def go_to_engineer(self, engineer):
        """Close (1000 light years or less): the galaxy map macro. Far away (or distance unknown): a neutron route from Spansh."""
        state = self.state_provider()
        fields = self._engineer_fields(engineer)
        here = str(getattr(state, "system", "") or "")
        if here.casefold() == engineer.system.casefold():
            self.narrator.say("EngineerHere", fields)
            return "%s is right here in %s" % (engineer.name, here)
        limit = self._engineer_limit()
        miles = fields["ly"]
        if miles is not None and miles <= limit and self.plot_macro is not None:
            ok, reason = self.plot_macro(engineer.system)
            if not ok:
                fields["reason"] = reason or "the galaxy map macro is not available"
                self.narrator.say("EngineerPlotOff", fields)
                return "Could not plot: %s" % fields["reason"]
            self.narrator.say("EngineerNear", fields)
            return "Plotting %s in %s with the galaxy map" % (engineer.name, engineer.system)
        if self._busy:
            return "Already plotting."
        self._busy = True
        self.narrator.say("EngineerFar" if miles is not None else "EngineerFarUnknown", fields)
        self.spawn(lambda: self._plot_now(engineer.system))
        return "Plotting a neutron route to %s in %s" % (engineer.name, engineer.system)

    def _engineer_limit(self):
        try:
            return float(self.settings.get("engineers.neutron_over_ly", 1000))
        except (TypeError, ValueError):
            return 1000.0

    def carrier_system(self, key):
        """Where is the carrier? Your own: what the journal says, else the 'Fleet carrier' bookmark. The squad's: the 'Squad carrier' bookmark."""
        state = self.state_provider()
        if key == "fleet":
            seen = str(getattr(state, "fleet_carrier_system", "") or "").strip()
            if seen:
                return seen
        return str(self.settings.get("bookmarks." + key, "") or "").strip()

    def _plot_carrier(self, key):
        name = self.carrier_system(key)
        state = self.state_provider()
        if not name:
            if key == "fleet":
                self.narrator.say("CarrierFleetUnknown")
                return "I don't know where your fleet carrier is."
            squad = str(getattr(state, "squadron", "") or "").strip()
            if squad:
                self.narrator.say("CarrierSquadUnknown", {"squadron": squad})
                return "I don't know where the squad carrier is."
            self.narrator.say("CarrierNoSquad")
            return "No squad carrier saved, and no squadron known."
        here = str(getattr(state, "system", "") or "")
        if here and here.casefold() == name.casefold():
            self.narrator.say("CarrierHere", {"system": name, "carrier": slot_name(key).lower()})
            return "We are already in %s." % name
        if self._busy:
            return "Already plotting."
        self._busy = True
        self.narrator.say("CarrierPlotting", {"destination": name, "carrier": slot_name(key).lower()})
        self.spawn(lambda: self._plot_now(name))
        return "Plotting a route to the %s in %s" % (slot_name(key).lower(), name)

    def _my_favourites(self):
        return {clean(k): v for k, v in (self.settings.get("neutron.favourites", {}) or {}).items()}

    def _destination_name(self, spoken):
        spoken = _TAIL.sub("", clean(spoken)).strip()
        if spoken.startswith("the ") and spoken not in FAVOURITES:
            spoken = spoken[4:]
        if spoken in ("my target", "the target", "target", "my target destination", "target destination", "where i am going", "where i m going"):
            return self._target_in_game() or str(self.settings.get("neutron.destination", "") or "").strip()
        if spoken in ("my destination", "destination", "the destination", "my saved destination", "my usual destination"):
            return self._target_in_game() or str(self.settings.get("neutron.destination", "") or "").strip()
        mine = self._my_favourites()
        if spoken in mine:
            return mine[spoken]
        key = slot_key(spoken)
        if key in ("fleet", "squad"):
            return self.carrier_system(key)
        if key is not None:
            return str(self.settings.get("bookmarks." + key, "") or "").strip()
        return FAVOURITES.get(spoken) or " ".join(w.capitalize() if not w.isupper() else w for w in spoken.split())

    def jump_range(self):
        try:
            manual = float(str(self.settings.get("neutron.jump_range", 0) or 0).strip())
        except ValueError:
            manual = 0.0
        if manual > 0:
            return manual
        state = self.state_provider()
        own = getattr(state, "max_jump_range", None) if state is not None else None
        if not own:
            return 0.0
        try:
            margin = float(self.settings.get("neutron.range_margin", 0.9))
        except (TypeError, ValueError):
            margin = 0.9
        return round(float(own) * margin, 2)

    def _plot_now(self, name):
        try:
            state = self.state_provider()
            here = getattr(state, "system", None) if state is not None else None
            rng = self.jump_range()
            if not here:
                self.narrator.say("RouteNoLocation")
                return
            if rng <= 0:
                self.narrator.say("RouteNoRange")
                return
            target = self.spansh.find_system(name)
            waypoints = self.spansh.neutron_route(
                here, target, rng, self.settings.get("neutron.efficiency", 60), self.supercharge())
            self.follower.set_route(waypoints, target, here)
            if not self.follower.active:
                self.narrator.say("RouteArrived", {"destination": target})
                return
            self.follower.copy_next()
            self.narrator.say("RouteReady", self.follower.fields())
            self.follower.maybe_auto_plot()
        except SpanshError as error:
            if self._spansh_does_not_know(here) and self.settings.get("neutron.emergency", True):
                self.emergency(name)
            else:
                self.narrator.say("RouteFailed", {"reason": str(error)})
        except Exception:
            log.exception("Plotting the route failed")
            self.narrator.say("RouteFailed", {"reason": "Something went wrong. The log has the details."})
        finally:
            self._busy = False

    # ---- the emergency protocol ----
    def _spansh_does_not_know(self, system):
        """True when Spansh answers that it has never heard of this system (so no route can start from here)."""
        try:
            self.spansh.find_system(system)
            return False
        except SpanshError as error:
            return str(error).startswith(("Spansh doesn't know", "I couldn't find a system like"))
        except Exception:
            return False

    def start_emergency(self):
        """'Emergency protocol': works out where you want to go (the target set in the game) and finds a way."""
        destination = self._target_in_game() or str(self.settings.get("neutron.destination", "") or "").strip()
        if not destination:
            self.narrator.say("RouteNoDestination")
            return "No destination."
        if self._busy:
            return "Already plotting."
        self._busy = True

        def work():
            try:
                self.emergency(self.spansh.find_system(destination))
            except SpanshError as error:
                self.narrator.say("RouteFailed", {"reason": str(error)})
            except Exception:
                log.exception("The emergency protocol failed")
                self.narrator.say("RouteFailed", {"reason": "Something went wrong. The log has the details."})
            finally:
                self._busy = False
        self.spawn(work)
        return "Emergency protocol: finding a known place near us."

    def emergency(self, destination):
        """Spansh can't start a route from here. Find the nearest landmark that Spansh DOES know, plot a course to it in
        the game, and (on arrival, see on_arrival) plot the neutron route from there to `destination`."""
        state = self.state_provider()
        position = getattr(state, "star_pos", None)
        if not position:
            self.narrator.say("EmergencyNoPosition")
            return False
        self.narrator.say("EmergencyStart", {"destination": destination})
        found = self._nearest_known_place(position)
        if found is None:
            self.narrator.say("EmergencyNone")
            return False
        miles = round(distance(position, found["coords"])) if found.get("coords") else 0
        self._set_emergency({"poi": found["system"], "destination": destination})
        fields = {"poi": found["system"], "place": found.get("poi") or found["system"], "distance": miles or "",
                  "destination": destination}
        self.set_target(found["system"])
        plot = getattr(self.follower, "auto_plot", None)
        if plot is not None and self.settings.get("neutron.auto_plot", False):
            self.narrator.say("EmergencyPlotting", fields)
            self.schedule_plot(plot)
        else:
            self.follower.copier(found["system"])
            self.narrator.say("EmergencyManual", fields)
        return True

    def schedule_plot(self, plot):
        threading.Timer(3.0, plot).start()

    def _nearest_known_place(self, position):
        """Ask EDAstro for the nearest landmark, then for better-rated ones, until Spansh knows the system by that exact name."""
        tried = set()
        for rating in (None, 2, 3, 4, 5):
            try:
                place = self.edastro.nearest(position, rating)
            except EdAstroError as error:
                self.narrator.say("RouteFailed", {"reason": str(error)})
                return None
            if not place or place["system"].casefold() in tried:
                continue
            tried.add(place["system"].casefold())
            try:
                exact = self.spansh.find_system(place["system"])
            except SpanshError:
                continue
            if exact.casefold() == place["system"].casefold():
                place["system"] = exact
                return place
        return None

    def on_arrival(self, event):
        """Arrived somewhere: if it is the landmark from the emergency protocol, plot the neutron route to the real destination."""
        waiting = self._emergency
        system = str((getattr(event, "data", None) or {}).get("StarSystem") or "")
        self._welcome_home(system)
        if not waiting or not system or system.casefold() != str(waiting.get("poi", "")).casefold():
            return
        self._set_emergency(None)
        self.narrator.say("EmergencyArrived", {"destination": waiting["destination"], "poi": system})
        if not self._busy:
            self._busy = True
            self.spawn(lambda: self._plot_now(waiting["destination"]))

    def _welcome_home(self, system):
        """Arriving in the system saved as Home (Navigation page > Bookmarks): she welcomes you back, at most once every 20 minutes."""
        home = str(self.settings.get("bookmarks.home", "") or "").strip()
        if not home or not system or home.casefold() != system.casefold():
            return
        now = self.clock()
        if self._home_said is not None and now - self._home_said < 1200:
            return
        self._home_said = now
        self.narrator.say("WelcomeHome", {"system": system})

    def _set_emergency(self, value):
        self._emergency = value
        try:
            if value:
                self.emergency_file.parent.mkdir(parents=True, exist_ok=True)
                self.emergency_file.write_text(json.dumps(value), encoding="utf-8")
            elif self.emergency_file.exists():
                self.emergency_file.unlink()
        except OSError:
            log.exception("Could not save the emergency route")

    def _load_emergency(self):
        try:
            data = json.loads(self.emergency_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) and data.get("poi") and data.get("destination") else None
        except (OSError, ValueError):
            return None
