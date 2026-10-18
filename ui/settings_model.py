"""
What the dashboard lets you change - written as a plain LIST so it is easy to update.

TO ADD A NEW SETTING TO THE DASHBOARD: add one line to the right page in PAGES below.
    Field("tts.volume", "Volume", "choice", choices=VOLUME, help="How loud she is")
The window is built from this list automatically; you do not touch the window code.

Kinds of field:
    "choice"  a drop-down menu
    "toggle"  an on/off switch
    "text"    a box you type in
A choice is a list of (label, value) pairs: the label is what you see, the value is what is saved.

This file contains no window code, so it is easy to test and cannot crash the window.
"""

import json
from dataclasses import dataclass, field as dc_field
from typing import Callable, List, Optional, Union

from core import paths
from core.logger import get_logger
from tts.kokoro_tts import BUILT_IN_VOICES

log = get_logger("dashboard")


@dataclass
class Field:
    key: str                                   # where it lives in settings.json, e.g. "tts.volume"
    label: str
    kind: str                                  # "choice", "toggle" or "text"
    choices: Union[List, Callable, None] = None
    help: str = ""
    restart: bool = False                      # True = only takes effect after restarting the app
    placeholder: str = ""


@dataclass
class Page:
    id: str
    title: str
    blurb: str
    fields: List[Field] = dc_field(default_factory=list)


# ---------------------------------------------------------------------------
# Lists of choices
# ---------------------------------------------------------------------------
VOLUME = [("Mute", 0)] + [("%d%%" % v, v) for v in range(10, 101, 10)]
SPEED = [("Very slow", -6), ("Slow", -3), ("Normal", 0), ("Fast", 3), ("Very fast", 6)]
MOODS = [("Neutral (calm, professional)", "Neutral"), ("Friendly", "Friendly"), ("Close (very happy, loving)", "Close"), ("Sarcastic (sassy)", "Sarcastic"),
         ("Frustrated", "Frustrated")]
LISTEN_QUALITY = [("Fast (smallest)", "tiny.en"), ("Balanced", "base.en"), ("Accurate (slower)", "small.en")]
SENSITIVITY = [("Automatic (recommended)", 0), ("Very sensitive (quiet room)", 0.008), ("Sensitive", 0.015),
               ("Normal", 0.025), ("Noisy room", 0.05)]
LOG_DETAIL = [("Normal", "INFO"), ("Detailed (for fixing problems)", "DEBUG"), ("Errors only", "WARNING")]
STYLES = [("Personality (banter, pet names, moods)", "personality"), ("Info only (plain and to the point)", "info")]
REMARKS = [("Never", "off"), ("Rarely", "rare"), ("Sometimes", "sometimes"), ("Often", "often")]
AFFECTION = [("Never", 0), ("After 100 million", 100000000), ("After 500 million", 500000000),
             ("After 1 billion", 1000000000)]
MOOD_MODES = [("Automatic (follows what I do in the game)", "auto"), ("Fixed (always the mood below)", "fixed")]
PTT_MODES = [("Off (say her name instead)", "off"), ("Hold the button while I talk", "hold"),
             ("Press once to start, again to stop", "toggle")]
HONK_MODES = [("Off", "off"), ("Primary fire button", "primary"), ("Secondary fire button", "secondary")]
FACT_FREQUENCY = [("Never", "off"), ("Rarely (about every 30 minutes)", "rarely"), ("Sometimes (about every 15 minutes)", "sometimes"),
                  ("Often (about every 8 minutes)", "often"), ("Very often (about every 4 minutes)", "very_often")]
FACT_TOPICS = [("Everything", "all"), ("Elite Dangerous lore and history", "elite"), ("Real space and the galaxy", "real"),
               ("Planet and star types", "planets")]
RECORD_SECONDS = [("10 seconds", 10), ("20 seconds", 20), ("30 seconds", 30), ("45 seconds", 45), ("60 seconds", 60)]
RECORD_COUNTDOWN = [("3 seconds", 3), ("5 seconds", 5), ("10 seconds", 10)]
RANGE_MARGIN = [("Full range (100%)", 1.0), ("Safe (95%)", 0.95), ("Safer, with cargo (90%)", 0.9), ("Heavy cargo (85%)", 0.85), ("Very heavy (80%)", 0.8)]
ROUTE_EFFICIENCY = [("Fewest jumps (40)", 40), ("Balanced (60)", 60), ("Most neutron stops (80)", 80), ("Strict neutron route (100)", 100)]
SUPERCHARGE = [("Normal (x4)", 4), ("Special (x6)", 6)]
WATCHER_REPLY = [("Every time", "always"), ("Often", "often"), ("Sometimes", "sometimes"), ("Never", "never")]
ANSWER_TIMES = [("5 seconds", 5), ("8 seconds", 8), ("10 seconds", 10), ("15 seconds", 15), ("20 seconds", 20)]
SEXES = [("Not specified", "neutral"), ("Male", "male"), ("Female", "female")]
VOICES = ([("Her own cloned voice", "")]
          + [("%s - female" % n, k) for k, n in BUILT_IN_VOICES.items() if k.startswith("af_")]
          + [("%s - male" % n, k) for k, n in BUILT_IN_VOICES.items() if k.startswith("am_")])


def microphone_choices(lister=None):
    """[("Windows default", ""), ("Headset Microphone (USB)", "Headset Microphone (USB)"), ...]"""
    if lister is None:
        from stt.microphone import list_microphones as lister
    found = [("Windows default", "")]
    seen = set()
    try:
        for _number, name in lister():
            if name not in seen:           # Windows lists the same microphone several times
                seen.add(name)
                found.append((name, name))
    except Exception:
        log.exception("Could not list microphones for the dashboard")
    return found


def voicepack_choices(folder=None):
    folder = folder or paths.VOICEPACKS_DIR
    found = []
    try:
        for child in sorted(folder.iterdir()):
            info = child / "pack.json"
            if child.is_dir() and (info.exists() or (child / "dialogue.json").exists()):
                name = child.name
                try:
                    name = json.loads(info.read_text(encoding="utf-8")).get("name") or child.name
                except (OSError, ValueError):
                    pass
                found.append(("%s" % name, child.name))
    except OSError:
        pass
    return found or [("Default", "default")]


# ---------------------------------------------------------------------------
# THE DASHBOARD CONTENT - edit here
# ---------------------------------------------------------------------------
def build_pages(mic_lister=None, pack_folder=None):
    return [
        Page("voice", "Voice", "How she sounds when she speaks.", [
            Field("speech.enabled", "She speaks aloud", "toggle", help="Turn her voice on or off"),
            Field("tts.volume", "Volume", "choice", VOLUME),
            Field("tts.rate", "Speaking speed", "choice", SPEED),
            Field("tts.voice", "Voice", "choice", VOICES,
                  help="All free and offline. A new voice downloads once (small) the first time you use it"),
        ]),
        Page("listening", "Listening", "How she hears you.", [
            Field("stt.enabled", "Listen when the app starts", "toggle", restart=True),
            Field("stt.microphone", "Microphone", "choice", lambda: microphone_choices(mic_lister), restart=True,
                  help="Pick the microphone you talk into"),
            Field("stt.model", "Listening quality", "choice", LISTEN_QUALITY, restart=True,
                  help="Bigger understands better but uses more memory"),
            Field("stt.energy_threshold", "Microphone sensitivity", "choice", SENSITIVITY, restart=True),
            Field("stt.wake_phrase", "Wake word", "text", restart=True,
                  placeholder="Leave empty to use her name",
                  help="What you say to get her attention. Empty = her name"),
            Field("stt.require_wake", "Only react when I say her name", "toggle"),
            Field("stt.reply", "She answers when she hears me", "toggle"),
        ]),
        Page("controls", "Controls", "Voice commands, push-to-talk and your joystick.", [
            Field("commands.enabled", "Voice commands", "toggle",
                  help="Say things like 'lower the landing gear' and she presses your key"),
            Field("commands.confirm", "She says what she did", "toggle",
                  help="Off = she only speaks up when something goes wrong"),
            Field("commands.require_game_focus", "Only press keys while Elite is in front", "toggle",
                  help="Safety: stops her typing into your browser or Discord. Leave this on"),
            Field("autohonk.mode", "Auto honk when I arrive in a system", "choice", HONK_MODES,
                  help="She holds your fire button for a few seconds. Pick the fire button your Discovery Scanner is on "
                       "(it needs a keyboard key as well as any joystick button)"),
            Field("voidcompass.enabled", "Control Void Compass overlays by voice", "toggle",
                  help="'Show the cargo overlay', 'hide all overlays'. In Void Compass switch on Settings > Integrations > Local API and Allow control"),
            Field("voidcompass.port", "Void Compass Local API port", "text", placeholder="7380",
                  help="Only change this if you changed it in Void Compass (it is 7380 out of the box)"),
            Field("watcher.enabled", "Answer the Watcher from Void Compass", "toggle",
                  help="When his voice is on in Void Compass she answers him in her mood. Needs the Local API on, as above"),
            Field("watcher.reply", "How often she answers him", "choice", WATCHER_REPLY),
            Field("watcher.wait_for_calm", "Make the Watcher wait for a calm moment", "toggle",
                  help="If he speaks while she is talking, during a warning, in a fight or while jumping, she cuts him off and he repeats it later"),
            Field("ptt.mode", "Push-to-talk", "choice", PTT_MODES,
                  help="With push-to-talk you do not need to say her name"),
            Field("ptt.button", "Push-to-talk button", "text", placeholder="Use the Learn button below",
                  help="A keyboard key, mouse side button or joystick button (your X52)"),
            Field("recorder.seconds", "Button recorder: how long it records", "choice", RECORD_SECONDS,
                  help="Use the Record my buttons button below. It watches your HOTAS and writes down what you press and when"),
            Field("recorder.countdown", "Button recorder: countdown before it starts", "choice", RECORD_COUNTDOWN),
            Field("ptt.beep", "Beep when the microphone opens", "toggle"),
            Field("ptt.skip_wake", "No need to say her name with push-to-talk", "toggle"),
        ]),
        Page("chat", "Chat and facts", "She asks you questions and shares things she has read. She needs listening switched on to hear your answers.", [
            Field("facts.frequency", "How often she offers a fact", "choice", FACT_FREQUENCY,
                  help="She offers when you arrive in a system. She asks first; say yes or no. Say 'Starling, tell me a fact' any time"),
            Field("facts.topics", "What the facts are about", "choice", FACT_TOPICS),
            Field("ask.scan_prompts", "Ask if we should scan valuable planets", "toggle",
                  help="Earth-like worlds, water worlds and other good finds. Saying nothing costs a little mood; saying no does not"),
            Field("ask.bio_prompts", "Wonder aloud about planets with life", "toggle",
                  help="She says 'shall we go and see what's down there?'. No answer is needed and it never changes her mood"),
            Field("ask.answer_seconds", "How long she waits for your answer", "choice", ANSWER_TIMES,
                  help="No answer in time counts as ignoring her (and for facts, as a no)"),
        ]),
        Page("navigation", "Navigation", "Neutron routes. Say 'Starling, plot a neutron route to Colonia'. She asks Spansh (spansh.co.uk) and copies each waypoint to your clipboard for the galaxy map search.", [
            Field("neutron.enabled", "Neutron route plotter", "toggle"),
            Field("neutron.destination", "My destination", "text", placeholder="e.g. Colonia",
                  help="Say 'plot a neutron route to my destination' and she uses this"),
            Field("neutron.jump_range", "Jump range in light years (0 = work it out)", "text", placeholder="0",
                  help="0 uses your ship's range from Elite, reduced by the setting below. Type your own laden range if she gets it wrong"),
            Field("neutron.range_margin", "Safety margin on the range", "choice", RANGE_MARGIN,
                  help="Elite's own figure is for an empty ship. Lower it if you carry cargo"),
            Field("neutron.efficiency", "Route style", "choice", ROUTE_EFFICIENCY),
            Field("neutron.supercharge", "Neutron boost", "choice", SUPERCHARGE,
                  help="Leave on Normal unless you know your ship gets x6"),
            Field("neutron.clipboard", "Copy the next waypoint to my clipboard", "toggle",
                  help="Then in the galaxy map: click search, Ctrl+V, Enter, and plot"),
            Field("neutron.auto_plot", "Plot each waypoint in the galaxy map for me", "toggle",
                  help="She runs the galaxy map macro by herself after a route is made and after each supercharge. "
                       "You can always say 'plot the next waypoint'. Needs the keys in Elite's controls (see the guide)"),
            Field("neutron.announce", "She tells me the next waypoint", "toggle"),
        ]),
        Page("updates", "Updates", "Starling.exe installs new versions from your GitHub releases by itself. This page lets you check by hand.", [
            Field("updates.repo", "GitHub repository", "text", placeholder="owner/name",
                  help="Filled in automatically when you start from Starling.exe"),
            Field("updates.auto_check", "Look for updates when Starling starts", "toggle",
                  help="A new version is downloaded in the background and installed the next time you open Starling.exe"),
            Field("updates.token", "GitHub token (only for a private repository)", "text",
                  help="Leave empty for a public repository. A token lets Starling read a private one. Keep it secret"),
        ]),
        Page("bookmarks", "Bookmarks", "Eleven places to keep system names. Say 'Starling, plot a neutron route to Home' or 'to bookmark 3'.",
             [Field("bookmarks.home", "Home", "text", placeholder="System name")]
             + [Field("bookmarks.b%d" % n, "Bookmark %d" % n, "text", placeholder="System name") for n in range(1, 11)]),
        Page("personality", "Personality", "Who she is today.", [
            Field("app.name", "Her name", "text", restart=True, placeholder="Starling",
                  help="Also the word that wakes her up (unless you set a wake word)"),
            Field("player.sex", "You are", "choice", SEXES,
                  help="Changes the pet names and compliments she uses (handsome, beautiful...)"),
            Field("personality.login_greeting", "Greet me when I load the game", "toggle",
                  help="Says your ship, where you are, and how she feels"),
            Field("personality.style", "Style", "choice", STYLES,
                  help="Info only = no jokes, pet names or moods"),
            Field("personality.mood_mode", "Mood control", "choice", MOOD_MODES,
                  help="Automatic: her mood changes with your actions (see Home)"),
            Field("personality.mood", "Fixed mood", "choice", MOODS,
                  help="Only used when Mood control is Fixed"),
            Field("personality.remarks", "Extra comments", "choice", REMARKS,
                  help="How often she adds a comment after a line"),
            Field("personality.pet_names", "Pet names", "toggle", help="Sweetheart, darling... or worse"),
            Field("personality.innuendo", "Flirty and naughty", "toggle",
                  help="Cheeky innuendo: flirty when she is Friendly or Close, grumpy-and-rude when she is Sarcastic or Frustrated"),
            Field("personality.dark_humour", "Dark humour", "toggle",
                  help="A little gallows humour now and then, in every mood (never during safety warnings)"),
            Field("personality.affection_credits", "Gets affectionate when rich", "choice", AFFECTION,
                  help="When the exobiology data you carry is worth more than this"),
            Field("personality.active_voicepack", "Voice pack", "choice", lambda: voicepack_choices(pack_folder),
                  restart=True),
            Field("speech.allow_mature", "Allow strong language", "toggle"),
        ]),
        Page("game", "Game", "How she watches Elite Dangerous.", [
            Field("journal.folder", "Journal folder", "text", restart=True,
                  placeholder="Leave empty to find it automatically"),
            Field("app.log_level", "Log detail", "choice", LOG_DETAIL, restart=True,
                  help="Only change this if you are fixing a problem"),
        ]),
    ]


class SettingsModel:
    """Holds the pages and keeps track of what you changed."""

    def __init__(self, settings, mic_lister=None, pack_folder=None):
        self.settings = settings
        self.pages = build_pages(mic_lister, pack_folder)
        self._saved = {f.key: settings.get(f.key) for p in self.pages for f in p.fields}
        self.pending_restart = set()
        self._cache = {}

    # ---- looking things up ----
    def all_fields(self):
        return [f for p in self.pages for f in p.fields]

    def field(self, key):
        for f in self.all_fields():
            if f.key == key:
                return f
        raise KeyError(key)

    def choices(self, field, refresh=False):
        """The list of (label, value) for a drop-down, plus the current value if it is not in the list."""
        if field.key not in self._cache or refresh:
            raw = field.choices() if callable(field.choices) else (field.choices or [])
            self._cache[field.key] = list(raw)
        options = list(self._cache[field.key])
        current = self.settings.get(field.key)
        if current not in [value for _label, value in options]:
            options.append(("Custom (%s)" % (current if current != "" else "none"), current))
        return options

    def labels(self, field):
        return [label for label, _value in self.choices(field)]

    def current_label(self, field):
        current = self.settings.get(field.key)
        for label, value in self.choices(field):
            if value == current:
                return label
        return str(current)

    def current_value(self, field):
        return self.settings.get(field.key)

    # ---- changing things ----
    def set_choice(self, field, label):
        for lab, value in self.choices(field):
            if lab == label:
                return self.set_value(field, value)
        return False

    def set_value(self, field, value):
        if field.kind == "toggle":
            value = bool(value)
        elif field.kind == "text":
            value = str(value or "").strip()
            if field.key == "app.name" and not value:
                value = "Starling"
        if self.settings.get(field.key) == value:
            return False
        self.settings.set(field.key, value)
        if field.restart and value != self._saved.get(field.key):
            self.pending_restart.add(field.key)
        elif field.key in self.pending_restart:
            self.pending_restart.discard(field.key)
        return True

    def dirty(self):
        return any(self.settings.get(k) != v for k, v in self._saved.items())

    def restart_needed(self):
        return bool(self.pending_restart)

    # ---- saving ----
    def save(self):
        """Write settings.json. Returns (True, "") or (False, "reason")."""
        try:
            self.settings.save()
        except OSError as error:
            log.exception("Could not save settings")
            return False, "Could not save: %s" % error
        self._saved = {k: self.settings.get(k) for k in self._saved}
        return True, ""

    def revert(self):
        """Throw away unsaved changes."""
        for key, value in self._saved.items():
            self.settings.set(key, value)
        self.pending_restart.clear()
