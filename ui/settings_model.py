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
from pathlib import Path
import re
from dataclasses import dataclass, field as dc_field
from typing import Callable, List, Optional, Union

from core import paths
from core.logger import get_logger
from mining import minerals
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
    parent: str = ""          # a page with a parent is shown as a section inside that page, not in the sidebar


# ---------------------------------------------------------------------------
# Lists of choices
# ---------------------------------------------------------------------------
VOLUME = [("Mute", 0)] + [("%d%%" % v, v) for v in range(10, 101, 10)]
SPEED = [("Very slow", -6), ("Slow", -3), ("Normal", 0), ("Fast", 3), ("Very fast", 6)]
MOOD_LEVELS = [("1 - just arrived", 1), ("2", 2), ("3 - middle", 3), ("4", 4), ("5 - nearly the next mood", 5)]
MOODS = [("Infatuated (head over heels)", "Infatuated"), ("Close (very happy, loving)", "Close"), ("Friendly", "Friendly"),
         ("Neutral (calm, professional)", "Neutral"), ("Sarcastic (sassy)", "Sarcastic"), ("Frustrated", "Frustrated"),
         ("Upset (really angry)", "Upset")]
LISTEN_QUALITY = [("Fast (smallest)", "tiny.en"), ("Balanced", "base.en"), ("Accurate (slower)", "small.en")]
SENSITIVITY = [("Automatic (recommended)", 0), ("Very sensitive (quiet room)", 0.008), ("Sensitive", 0.015),
               ("Normal", 0.025), ("Noisy room", 0.05)]
LOG_DETAIL = [("Normal", "INFO"), ("Detailed (for fixing problems)", "DEBUG"), ("Errors only", "WARNING")]
STYLES = [("Personality (banter, pet names, moods)", "personality"), ("Info only (plain and to the point)", "info")]
WARM = [("When the CPU is free (recommended)", "idle"), ("Off", "off")]
CHITCHAT = [("Rarely", "rarely"), ("Normal", "normal"), ("Often", "often"), ("Chatty", "chatty")]
REMARKS = [("Never", "off"), ("Rarely", "rare"), ("Sometimes", "sometimes"), ("Often", "often")]
AFFECTION = [("Never", 0), ("After 100 million", 100000000), ("After 500 million", 500000000),
             ("After 1 billion", 1000000000)]
MINERAL_CHOICES = minerals.choices()      # every mineral, metal and ice you can mine (mining/minerals.py)
MINING_CHATTER = [("Quiet (first of each, every 10 tonnes)", "quiet"), ("Normal (every 5 tonnes, a few cheers)", "normal"),
                  ("Chatty (every 3 tonnes, lots of cheers)", "chatty")]
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
MERIT_POWERS = [("From the game (what the journal says)", "")] + [(p, p) for p in (
    "Aisling Duval", "Archon Delaine", "Arissa Lavigny-Duval", "Denton Patreus", "Edmund Mahon", "Felicia Winters",
    "Jerome Archer", "Li Yong-Rui", "Nakato Kaine", "Pranav Antal", "Yuri Grom", "Zemina Torval")]
WATCHER_REPLY = [("Every time", "always"), ("Often", "often"), ("Sometimes", "sometimes"), ("Never", "never")]
ANSWER_TIMES = [("5 seconds", 5), ("8 seconds", 8), ("10 seconds", 10), ("15 seconds", 15), ("20 seconds", 20)]
MESSAGE_CHANNELS = [("Direct messages only", "direct"), ("Direct, friends, wing and squadron", "direct_plus"),
                    ("Everything, including local and system chat", "all")]
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


_VERSION_TAIL = re.compile(r"\.\d+\.\d+$")


def preset_choices(folder=None):
    """The control presets Elite has saved, for the Keybinds page drop-downs:
    [("Automatic (she works it out)", ""), ("HCS Custom", "HCS Custom"), ("MCUSTOM", "MCUSTOM"), ...]"""
    found = [("Automatic (she works it out)", "")]
    try:
        from control import binds
        folder = folder if folder is not None else binds.bindings_folder()
        names = {}
        if folder is not None and Path(folder).is_dir():
            for path in sorted(Path(folder).glob("*.binds")):
                name = _VERSION_TAIL.sub("", path.name[:-len(".binds")])
                names.setdefault(name.lower(), name)
        for name in sorted(names.values(), key=str.lower):
            found.append((name, name))
    except Exception:
        log.exception("Could not list the Elite control presets for the dashboard")
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


# These pages are not in the sidebar: they appear as a section inside the page named on the right.
SECTION_OF = {"listening": "voice", "controls": "game", "chat": "personality", "memory": "personality",
              "bookmarks": "navigation"}


# ---------------------------------------------------------------------------
# THE DASHBOARD CONTENT - edit here
# ---------------------------------------------------------------------------
def build_pages(mic_lister=None, pack_folder=None):
    pages = [
        Page("keybinds", "Keybinds", "Elite lets each group of controls use its own PRESET (look at the top of each controls page in Elite: Options > Controls, where it says PRESETS). "
             "Choose the preset for each group from the list (she lists every preset saved in Elite's controls folder, and the name must match the one the game shows at the top of that controls page). Leave a box on Automatic and she works it out. Restart Starling after changing one. "
             "Press Check my Elite keys below to see which files she found and which commands still have no key. She only gives you the list of missing keys; you set them yourself in Elite and she never changes any of your keys.", [
            Field("keybinds.ship", "Ship controls preset", "choice", preset_choices, restart=True,
                  help="Flying, panels, galaxy map, scanners. Empty = the one Elite starts with"),
            Field("onfoot.preset", "On foot controls preset", "choice", preset_choices, restart=True,
                  help="Walking, weapons, emotes, suit tools. Empty = she looks for it"),
            Field("keybinds.srv", "SRV controls preset", "choice", preset_choices, restart=True,
                  help="The surface vehicle. Empty = same file as the ship"),
            Field("keybinds.fighter", "Ship-launched fighter preset", "choice", preset_choices, restart=True,
                  help="Fighter orders and flying a fighter. Empty = same file as the ship"),
            Field("keybinds.multicrew", "Multicrew preset", "choice", preset_choices, restart=True,
                  help="Flying with another commander. Empty = same file as the ship"),
        ]),
        Page("voice", "Voice", "How she sounds when she speaks.", [
            Field("speech.enabled", "She speaks aloud", "toggle", help="Turn her voice on or off"),
            Field("tts.volume", "Volume", "choice", VOLUME),
            Field("tts.rate", "Speaking speed", "choice", SPEED),
            Field("tts.warm_cache", "Get new lines ready in the background", "choice", WARM,
                  help="Makes her new sentences ahead of time, only when you are docked or the game is off, so she answers faster"),
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
            Field("voidcompass.enabled", "Control Void Compass overlays by voice", "toggle",
                  help="'Show the cargo overlay', 'hide all overlays'. In Void Compass switch on Settings > Integrations > Local API and Allow control"),
            Field("voidcompass.port", "Void Compass Local API port", "text", placeholder="7380",
                  help="Only change this if you changed it in Void Compass (it is 7380 out of the box)"),
            Field("watcher.enabled", "Answer the Watcher from Void Compass", "toggle",
                  help="When his voice is on in Void Compass she answers him in her mood. Needs the Local API on, as above"),
            Field("watcher.reply", "How often she answers him", "choice", WATCHER_REPLY),
            Field("watcher.hush", "Ask Void Compass to keep the Watcher quiet while she talks", "toggle",
                  help="Needs a recent Void Compass (it has a 'hush' call). If your version has none she notices and stops asking"),
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
            Field("ask.answer_seconds", "How long she waits for your answer", "choice", ANSWER_TIMES,
                  help="No answer in time counts as ignoring her (and for facts, as a no)"),
        ]),
        Page("combat", "Combat", "Fighting: what she says, and the helpers that press keys for you.", [
            Field("talk.combat", "She comments on combat", "toggle",
                  help="Ship names, bounties, wanted targets, interdictions, wings and kills. Off = quiet, but safety warnings (under attack, shields, heat, hull) are never silenced"),
            Field("combat_assist.pips", "Combat: pips to weapons while I fire", "toggle",
                  help="While your hardpoints are out she puts the pips in weapons when you hold a fire button, and back to systems and engines when you let go. Uses your Primary/Secondary fire buttons from Elite"),
            Field("combat_assist.pips_analysis", "Combat: also in analysis mode (mining lasers)", "toggle",
                  help="The same pips to weapons while you hold a fire button, but when the cockpit is in analysis mode instead of hardpoints out"),
            Field("combat_assist.x52_trigger", "Joystick trigger counts as fire 1 and 2 (any HOTAS)", "toggle",
                  help="Buttons 1 and 2 of your flight stick (any make: X52, X56, Warthog, T16000M, VKB, Virpil...) (both trigger stages) always send pips to weapons, even if Elite's controls do not list them"),
            Field("combat_assist.heat_sink", "Combat: deploy a heat sink when overheating", "toggle",
                  help="Elite does not share the heat percentage, so she uses the game's own overheat warning (about 100%). Never while docked, landed or scooping"),
        ]),
        Page("onfoot", "On foot", "Voice control for everything on foot. Say 'suit shields', 'torch', 'next grenade type', 'select EMP grenades', 'use a health pack', 'use a battery', 'helmet night vision', 'energy link', 'crouch', 'wave'... Each needs a keyboard key in Elite's on-foot controls. Emote words are in config/emotes.json (docs/PHASE6_GUIDE.md).", [
            Field("onfoot.auto_shields", "On foot: raise my suit shields when I draw a weapon or take damage", "toggle",
                  help="Presses your Toggle Shields key once. Elite has only a toggle and does not say if the shields are up, so if they were already up they go down (say 'suit shields' to flip them back). Needs a keyboard key for Toggle Shields. In a fight (a combat bond, a bounty or damage) she keeps them up for 2 minutes and does not lower them when you holster; otherwise they go down when you holster. The game has no combat-zone flag, so she cannot raise them before the first sign of a fight"),
            Field("onfoot.auto_health", "On foot: use a medical pack when my health is 20% or lower", "toggle",
                  help="Presses your Health Pack key. Only if your backpack still has one (read from Backpack.json). Waits 6 seconds between uses"),
            Field("onfoot.auto_battery", "On foot: use an energy cell when my suit energy is 20% or lower", "toggle",
                  help="Uses the suit energy if the game puts it in Status.json (the log says if she found it). If it does not, she falls back to the first loss of health as the sign your shields are gone. Only if your backpack still has an energy cell. Waits 25 seconds between uses"),
            Field("onfoot.last_grenade_callout", "On foot: tell me when I throw my last grenade of a type", "toggle",
                  help="Reads your backpack counts (Backpack.json). Low ammo for guns cannot be called out because the game does not share ammo"),
        ]),
        Page("exploration", "Exploration", "Scanning, discoveries, fuel scooping and the honk.", [
            Field("talk.exploration", "She comments on exploration", "toggle",
                  help="Scans of interesting bodies, signals, codex finds, exploration data sales and fuel scooping. Off = quiet, safety warnings are never silenced"),
            Field("regions.announce", "Announce the galaxy region I enter", "toggle",
                  help="Says the region's name when you jump into a new one, and when it is your first time there"),
            Field("ask.scan_prompts", "Ask if we should scan valuable planets", "toggle",
                  help="Earth-like worlds, water worlds and other good finds. Saying nothing costs a little mood; saying no does not"),
            Field("nomad.stow_hardpoints", "Put the hardpoints away when the Nomad docks", "toggle",
                  help="When you recover the Nomad she retracts your hardpoints a moment later, if they are out"),
            Field("autohonk.mode", "Auto honk when I arrive in a system", "choice", HONK_MODES,
                  help="She holds your fire button for a few seconds. Pick the fire button your Discovery Scanner is on "
                       "(it needs a keyboard key as well as any joystick button)"),
        ]),
        Page("exobiology", "Exobiology", "Biological samples on planets.", [
            Field("talk.exobiology", "She comments on exobiology", "toggle",
                  help="The value on the first sample, what it is on the second, and selling biological data. Off = quiet"),
            Field("exobiology.distance_alert", "Tell me when I'm far enough from the last sample", "toggle",
                  help="After a sample she watches how far you walk and says when you can take the next one (the distance depends on the species)"),
            Field("exobiology.distance_beep", "Beep as well", "toggle", help="Two short beeps (Windows) just before she speaks"),
            Field("ask.bio_prompts", "Wonder aloud about planets with life", "toggle",
                  help="She says 'shall we go and see what's down there?'. No answer is needed and it never changes her mood"),
            Field("personality.affection_credits", "Gets affectionate when rich", "choice", AFFECTION,
                  help="When the exobiology data you carry is worth more than this"),
        ]),
        Page("mining", "Mining", "Pick the ten minerals she gets EXCITED about (she calls them out with a cheer). Osmium, palladium, bromellite "
             "and benitoite get a calmer mention. Everything else, gold and silver included, she keeps quiet about.", [
            Field("talk.mining", "She comments on mining", "toggle",
                  help="Prospector results, refining, cracked cores and depleted rocks. Off = quiet"),
            Field("mining.merit", "Find merit mining spots (\"I want to go merit mining\")", "toggle",
                  help="Looks on Spansh for a system your Power controls with a pristine metallic ring and a station wanting 2000+ tonnes, then asks 'the first one or the second one?' and plots the route"),
            Field("merit.power", "Your Power for merit mining", "choice", MERIT_POWERS,
                  help="Leave on 'From the game' and she reads it from the journal when you load the game while pledged"),
            Field("mining.destination_reminder", "Tell me the station when I reach the system she plotted", "toggle",
                  help="After she plots a route for selling, buying or merit mining, she names the station when you jump into that system"),
            Field("mining.limpet_reminder", "Remind me to buy limpets when I dock", "toggle",
                  help="Only if the ship you are flying has a refinery, a collector limpet controller and cargo racks, and you carry fewer than 100 limpets"),
            Field("mining.chatter", "How chatty she is while you refine", "choice", MINING_CHATTER,
                  help="She does not call out every tonne: the first of each good mineral, then every few tonnes"),
        ] + [Field("mining.fav%d" % n, "Excited about #%d" % n, "choice", MINERAL_CHOICES) for n in range(1, 11)]),
        Page("trading", "Trading", "Buying and selling, shopping and prices.", [
            Field("talk.trading", "She comments on trading and shopping", "toggle",
                  help="Market sales and purchases, buying a new ship or module. Off = quiet"),
            Field("mining.prices", "Look up the best prices online (sell and buy)", "toggle",
                  help="Ask her 'where should I sell the platinum' or 'where can I buy tritium'. Uses the free Ardent price service (needs internet, no sign-up)"),
        ]),
        Page("antixeno", "Anti-Xeno", "Fighting the Thargoids.", [
            Field("talk.antixeno", "She calls out Thargoid ships", "toggle",
                  help="When you target a Thargoid (scout, cyclops, basilisk, medusa, hydra, orthrus...) she names it. Off = quiet, safety warnings are never silenced"),
        ]),
        Page("navigation", "Navigation", "Neutron routes. Say 'Starling, plot a neutron route to Colonia'. She asks Spansh (spansh.co.uk) and copies each waypoint to your clipboard for the galaxy map search.", [
            Field("neutron.enabled", "Neutron route plotter", "toggle"),
            Field("engineers.neutron_over_ly", "Engineer farther than this many light years: neutron route", "text", placeholder="1000",
                  help="\"Take me to Felicity Farseer\": closer than this she uses the galaxy map plotter, farther she asks Spansh for a neutron route"),
            Field("neutron.destination", "My destination", "text", placeholder="e.g. Colonia",
                  help="Say 'plot a neutron route to my destination' and she uses this"),
            Field("neutron.jump_range", "Jump range in light years (0 = work it out)", "text", placeholder="0",
                  help="0 uses your ship's range from Elite, reduced by the setting below. Type your own laden range if she gets it wrong"),
            Field("neutron.range_margin", "Safety margin on the range", "choice", RANGE_MARGIN,
                  help="Elite's own figure is for an empty ship. Lower it if you carry cargo"),
            Field("neutron.efficiency", "Route style", "choice", ROUTE_EFFICIENCY),
            Field("neutron.supercharge", "Neutron boost", "choice", SUPERCHARGE,
                  help="Leave on Normal unless you know your ship gets x6. The Caspian Explorer is switched to x6 for you (next setting)"),
            Field("neutron.auto_x6", "Use x6 automatically in the Caspian Explorer", "toggle",
                  help="The Caspian is the only ship that gets the x6 boost, so when you fly it she plots with x6 and ignores the setting above"),
            Field("neutron.emergency", "Emergency protocol when Spansh can't find me", "toggle",
                  help="If Spansh does not know the system you are in, she finds the nearest landmark that it does know (using EDAstro), "
                       "plots a course there in the game, and plots the neutron route from there. You can also say 'emergency protocol'"),
            Field("neutron.auto_on_target", "Plot a neutron route by itself when I set a target", "toggle",
                  help="Off = you ask her by voice ('plot a neutron route'). On: pick a destination in the galaxy map and she works out the neutron route to it by herself. "
                       "Her own waypoint plotting and 'where to sell' targets are ignored"),
            Field("neutron.clipboard", "Copy the next waypoint to my clipboard", "toggle",
                  help="Then in the galaxy map: click search, Ctrl+V, Enter, and plot"),
            Field("neutron.auto_plot", "Plot each waypoint in the galaxy map for me", "toggle",
                  help="She runs the galaxy map macro by herself after a route is made and after each supercharge. "
                       "You can always say 'plot the next waypoint'. Needs the keys in Elite's controls (see the guide)"),
            Field("neutron.announce", "She tells me the next waypoint", "toggle"),
        ]),
        Page("memory", "Memory", "What she remembers about you and your trips. It is kept only on this computer, in data/tetko.db.", [
            Field("memory.enabled", "She remembers milestones", "toggle",
                  help="Longest jump, biggest sales, times destroyed, big missions, hours together. Off = nothing new is saved"),
            Field("memory.recall_at_login", "She mentions one memory when I log in", "toggle"),
        ]),
        Page("updates", "Updates", "Starling.exe installs new versions from your GitHub releases by itself. This page lets you check by hand.", [
            Field("updates.repo", "GitHub repository", "text", placeholder="owner/name",
                  help="Filled in automatically when you start from Starling.exe"),
            Field("updates.auto_check", "Look for updates when Starling starts", "toggle",
                  help="A new version is downloaded in the background and installed the next time you open Starling.exe"),
            Field("updates.ask", "Ask me before updating when I open Starling.exe", "toggle",
                  help="On: a separate 'Update available' screen appears before she loads (Update now / Not now). Off (the default): updates install by themselves when you open Starling.exe"),
            Field("updates.token", "GitHub token (only for a private repository)", "text",
                  help="Leave empty for a public repository. A token lets Starling read a private one. Keep it secret"),
        ]),
        Page("bookmarks", "Bookmarks", "Places to keep system names. Say 'Starling, plot a neutron route to Home', 'to bookmark 3', 'to my fleet carrier' or 'to the squad carrier'.",
             [Field("bookmarks.home", "Home", "text", placeholder="System name"),
              Field("bookmarks.fleet", "Fleet carrier", "text", placeholder="Filled in from the journal"),
              Field("bookmarks.squad", "Squad carrier", "text", placeholder="System name")]
             + [Field("bookmarks.b%d" % n, "Bookmark %d" % n, "text", placeholder="System name") for n in range(1, 11)]),
        Page("personality", "Personality", "Who she is today.", [
            Field("app.name", "Her name", "text", restart=True, placeholder="Starling",
                  help="Also the word that wakes her up (unless you set a wake word)"),
            Field("player.sex", "You are", "choice", SEXES,
                  help="Changes the pet names and compliments she uses (handsome, beautiful...)"),
            Field("personality.login_greeting", "Greet me when I load the game", "toggle",
                  help="Says your ship, where you are, and how she feels"),
            Field("messages.read", "Read my incoming messages out loud", "toggle",
                  help="She waits until nothing else is happening"),
            Field("messages.channels", "Which messages she reads", "choice", MESSAGE_CHANNELS,
                  help="Direct messages only (the default) keeps her quiet in busy systems. Local and system chat are only read with Everything"),
            Field("messages.npc", "Also read computer-controlled ships and stations", "toggle",
                  help="Off by default: pirates, stations and police talk a lot"),
            Field("plans.ask", "Ask me 'What are we doing today?'", "toggle",
                  help="After the hello she asks. Say exploring, mining, combat, trading, exobiology or Thargoids. One of them she is not in the mood for"),
            Field("personality.style", "Style", "choice", STYLES,
                  help="Info only = no jokes, pet names or moods"),
            Field("personality.mood_mode", "Mood control", "choice", MOOD_MODES,
                  help="Automatic: her mood changes with your actions (see Home)"),
            Field("personality.mood", "Fixed mood", "choice", MOODS,
                  help="Only used when Mood control is Fixed"),
            Field("personality.mood_level", "Fixed mood level (1-5)", "choice", MOOD_LEVELS,
                  help="Only used when Mood control is Fixed. Each mood has 5 steps: 1 = just arrived, 5 = nearly the next mood up (the friendliest)"),
            Field("personality.remarks", "Extra comments", "choice", REMARKS,
                  help="How often she adds a comment after a line"),
            Field("brain.enabled", "Her brain: answers to almost anything", "toggle",
                  help="Ask her about herself, the game, jokes, riddles, advice, or say hello to chat. Needs her name or push-to-talk"),
            Field("chitchat.enabled", "Small talk when it is quiet", "toggle",
                  help="Little jokes and comments after a quiet spell. About the fight in combat mode, about exploring in analysis mode"),
            Field("chitchat.frequency", "How often she chats", "choice", CHITCHAT,
                  help="Normal is about every 5 to 8 quiet minutes, Chatty about every 2 to 3"),
            Field("personality.pet_names", "Pet names", "toggle", help="Sweetheart, darling... or worse"),
            Field("personality.custom_pet_names", "My own pet names", "text", placeholder="e.g. Captain Fluffy, Sparky, Boss",
                  help="Type your own names for you, separated by commas. She mixes them in with her own whenever she uses a pet name"),
            Field("personality.innuendo", "Flirty and naughty", "toggle",
                  help="Cheeky innuendo: flirty when she is Friendly or Close, grumpy-and-rude when she is Sarcastic or Frustrated"),
            Field("personality.dark_humour", "Dark humour", "toggle",
                  help="A little gallows humour now and then, in every mood (never during safety warnings)"),
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
        Page("developer", "Developer", "Tests and tools for finding out why something does not work. Nothing here changes how she behaves.", []),
    ]
    for page in pages:
        page.parent = SECTION_OF.get(page.id, "")
    return pages


class SettingsModel:
    """Holds the pages and keeps track of what you changed."""

    def __init__(self, settings, mic_lister=None, pack_folder=None):
        self.settings = settings
        self.pages = build_pages(mic_lister, pack_folder)
        self.sidebar_pages = [p for p in self.pages if not p.parent]
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
