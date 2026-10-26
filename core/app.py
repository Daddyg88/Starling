"""
The App class: starts STARLING's parts in the right order and stops them safely.

Later phases will plug the voice, dashboard and so on in here.
"""

import platform
import sys
from datetime import datetime

from core import paths
from core.event_bus import ALL_EVENTS, EventBus
from core.logger import get_logger, setup_logging, shutdown_logging
from core.settings import Settings, load_event_config
from database.db import Database
from events.registry import load_registry
from journal.console_printer import print_event
from journal.event_logger import EventLogger
from journal.game_state import GameState
from journal.locator import find_journal_folder
from journal.monitor import JournalMonitor
from journal.processor import EventProcessor
from personality.dialogue import DialogueManager
from personality.speaker import EventSpeaker, load_rules
from personality.voice_replies import VoiceReplies
from journal.exobiology import ExobiologyTracker
from tts.providers import build_providers
from tts.speech_manager import SpeechManager

APP_NAME = "STARLING"
from core.version import __version__
APP_VERSION = __version__ + " (Phase 7: memory, combat, brain, mining)"


class App:
    def __init__(self, settings_path=None, database_path=None, logs_dir=None):
        self._settings_path = settings_path
        self._database_path = database_path
        self._logs_dir = logs_dir
        self.settings = None
        self.event_config = {}
        self.database = None
        self.bus = None
        self.session_id = None
        self.started_at = None
        self.log = None
        self.state = None
        self.registry = {}
        self.processor = None
        self.monitor = None
        self.journal_folder = None
        self.providers = {}
        self.speech = None
        self.dialogue = None
        self.speaker = None
        self.listener = None
        self.mood = None
        self.greeter = None
        self.memory_store = None
        self.event_logger = None
        self.memory_keeper = None
        self.memory_recall = None
        self.chitchat = None
        self.warmer = None
        self.smalltalk = None
        self.brain = None
        self.miner = None
        self.prices = None
        self.lore = None
        self.eoc = None
        self._record_events = True
        self.voice_replies = None
        self.manners = None
        self.learning = None
        self.flavour = None
        from control.echo import Echo
        self.echo = Echo()
        self.commands = None
        self.autohonk = None
        self.combat_assist = None
        self.watcher = None
        self.region_tracker = None
        self.bio_distance = None
        self.auto_shields = None
        self.onfoot_care = None
        self.route_voice = None
        self.route_follower = None
        self.ask = None
        self.ptt = None
        self.buttons = None
        self.stt_providers = {}

    # ---- starting up ----
    def start(self, record_events=True, show_events=False):
        self._record_events = record_events
        paths.ensure_folders()

        # Load settings first, because they say how chatty the log should be.
        self.settings = Settings(self._settings_path).load()
        try:
            from control import binds as _binds
            _binds.set_preset_names(self.settings)
        except Exception:
            pass
        if not self.settings.get("updates.ask_reset", False):
            # 0.41.1: updates install by themselves again. An older saved "ask me first" is switched off ONCE; switch it on again if you want it.
            self.settings.set("updates.ask", False)
            self.settings.set("updates.ask_reset", True)
            try:
                self.settings.save()
            except OSError:
                pass
        setup_logging(self.settings.get("app.log_level", "INFO"), self._logs_dir)
        self.log = get_logger("app")
        self.log.info("%s %s starting (Python %s)", APP_NAME, APP_VERSION, platform.python_version())

        self.event_config = load_event_config()
        self.database = Database(self._database_path).initialise()

        self.bus = EventBus()
        self.bus.subscribe(ALL_EVENTS, self._log_event)

        self.session_id = self.database.execute("INSERT INTO sessions DEFAULT VALUES")
        self.started_at = datetime.now()

        # Game knowledge and event handling
        self.state = GameState()
        self.state.exobiology = ExobiologyTracker(paths.CONFIG_DIR / "exobiology_values.json", paths.DATA_DIR)
        self.registry = load_registry()
        self.processor = EventProcessor(self.bus, self.event_config, self.state, self.registry)
        if record_events:
            saver = EventLogger(self.database, self.session_id)
            saver.trim_old()
            saver.attach(self.bus)
            self.event_logger = saver
        if show_events:
            self.bus.subscribe(ALL_EVENTS, print_event)

        from memory.store import MemoryStore
        self.memory_store = MemoryStore(self.database)
        if record_events:                          # --demo never writes memories
            from memory.keeper import MemoryKeeper
            self.memory_keeper = MemoryKeeper(self.bus, self.memory_store, self.settings, state_provider=lambda: self.state)
            self.memory_keeper.attach()

        self.bus.publish("app.started", {"session_id": self.session_id})
        self.log.info("%s online.", APP_NAME)

    def start_speech(self):
        """Give STARLING her voice. Returns True if she is ready to speak."""
        if not self.settings.get("speech.enabled", True):
            self.log.info("Speech is switched off in settings.json")
            return False
        self.providers = build_providers(self.settings)
        kokoro = self.providers.get("kokoro")
        if kokoro is not None:
            kokoro.start_loading()   # background thread: the game is never held up
        rules = load_rules()
        self.speech = SpeechManager(self.providers, self.settings, self.bus, rules["max_age_seconds"])
        self.speech.start()

        pack_name = self.settings.get("personality.active_voicepack", "default")
        self.dialogue = DialogueManager(
            paths.VOICEPACKS_DIR / pack_name,
            [paths.DIALOGUE_DIR / "core_lines.json"],
        ).load()
        missing = self.dialogue.missing_audio()
        if missing:
            self.log.warning("%d dialogue lines name an mp3 that is missing", len(missing))

        from personality.flavour import Flavour
        flavour = Flavour(self.dialogue, self.settings,
                          lambda: self.state.exobiology.carried_total() if self.state and self.state.exobiology else 0)
        self.flavour = flavour
        self.speaker = EventSpeaker(self.bus, self.speech, self.dialogue, self.settings, rules, flavour=flavour, echo=self.echo)
        self.speaker.attach()

        # Her mood follows what you do in the game (not saved during --demo).
        from personality.mood_engine import MoodEngine
        self.mood = MoodEngine(self.bus, self.settings, dialogue=self.dialogue, persist=self._record_events,
                               wanted_provider=lambda: bool(self.state and self.state.wanted),
                               speak=lambda text: self.speech.say(text=text, priority="normal", event_name="mood.react")
                               if self.speech is not None else None)
        self.mood.attach()
        self.mood.start_timer()                 # ends her temporary moods on time
        from personality.favourite_ship import FavouriteShip
        self.favourite_ship = FavouriteShip(
            lambda: self.state, self.settings, persist=self._record_events,
            say=lambda key, fields: self._say_line(key, fields))
        self.mood.good_listener = self.favourite_ship.add

        # Questions she asks out loud (facts, valuable planets, life) and the yes/no answers.
        from personality.ask import AskManager
        from personality.facts import FactBook
        self.ask = AskManager(self.bus, self.speech, self.dialogue, self.settings,
                              FactBook(self.dialogue, persist=self._record_events),
                              state_provider=lambda: self.state,
                              listening_provider=lambda: self.listener is not None and self.listener.ready.is_set(),
                              plot_provider=lambda system: self.plot_system_by_macro(system))
        self.ask.attach()
        self.ask.schedule_midgame(self.game_is_active)       # started while already playing: ask after a moment

        # The Watcher (Void Compass's orb): she answers him, and makes him wait for a calm moment.
        self.start_watcher_bridge()

        # Incoming chat messages, read out when nothing else is happening.
        from personality.messages import MessageReader
        self.message_reader = MessageReader(self.bus, self.speech, self.dialogue, self.settings,
                                            state_provider=lambda: self.state, ask_provider=lambda: self.ask)
        self.message_reader.attach()

        # The hello when you load into the game: ship, where you are, and how she feels.
        from personality.greeter import LoginGreeter
        from memory.recall import MemoryRecall
        self.memory_recall = MemoryRecall(self.memory_store, self.dialogue, self.settings, speech=self.speech)
        self.greeter = LoginGreeter(self.bus, self.speech, self.dialogue, self.settings,
                                    state_provider=lambda: self.state, flavour=flavour, memory=self.memory_recall, mood=self.mood)
        self.greeter.attach()

        # Gets new lines ready in the background when the CPU is free (see tts/voice_warmer.py).
        if kokoro is not None:
            from tts.voice_warmer import VoiceWarmer
            self.warmer = VoiceWarmer(kokoro, self.dialogue, self.settings, speech=self.speech,
                                      free_provider=self.cpu_is_free)
            if str(self.settings.get("tts.warm_cache", "idle")).lower() != "off":
                self.warmer.start()

        # Small talk when it has been quiet (only while Status.json shows the game is running).
        from personality.chitchat import ChitChat
        self.chitchat = ChitChat(self.bus, self.speech, self.dialogue, self.settings, state_provider=lambda: self.state,
                                 active_provider=self.game_is_active, memory=self.memory_recall)
        self.chitchat.attach()
        self.chitchat.start()
        from personality.smalltalk import SmallTalk
        from personality.lore import LoreTeller
        self.lore = LoreTeller(self.speech, self.dialogue, self.settings, path=paths.DATA_DIR / "lore.json")
        from personality.eoc import EOCTeller
        self.eoc = EOCTeller(self.speech, self.dialogue, self.settings, state_provider=lambda: self.state)
        self.smalltalk = SmallTalk(self.speech, self.dialogue, self.settings, chitchat=self.chitchat, mood=self.mood, lore=self.lore,
                                   eoc=self.eoc, favourite=getattr(self, "favourite_ship", None))
        from personality.brain import Brain
        from mining import minerals
        minerals.bind(self.settings)          # the Mining page's ten favourite minerals
        from mining.tracker import MiningTracker
        from mining.prices import PriceFinder
        self.miner = MiningTracker(self.bus)
        self.miner.attach()
        self.prices = PriceFinder(self.settings)
        from mining.merit import MeritFinder
        self.merit = MeritFinder(self.settings)
        self.brain = Brain(self.speech, self.dialogue, self.settings, state_provider=lambda: self.state, chitchat=self.chitchat,
                           facts=getattr(self.ask, "facts", None), mining=self.miner, prices=self.prices, ask=self.ask, merit=self.merit)
        return True

    def cpu_is_free(self):
        """True when the game is not running, you are in a menu, or you are docked: a good time to prepare her voice."""
        try:
            return (not self.game_is_active()) or bool(self.state and self.state.docked)
        except Exception:
            return False

    def prepare_voice_now(self):
        """Dashboard button. Returns a sentence for the screen (the dashboard also shows a progress bar)."""
        if self.warmer is None:
            return "Her voice is not set up, so there is nothing to prepare."
        if self.warmer.finished and not self.warmer.force:
            return self.warmer.status()
        if not self.warmer.force:
            self.warmer.run_now()
        return "Preparing her voice in the background. It uses some CPU for a few minutes, and you can keep using the dashboard."

    def game_is_active(self):
        """True while you are in the cockpit or on foot and Elite is still writing Status.json."""
        import time as _time
        try:
            if not (self.state and self.state.status_seen) or self.monitor is None:
                return False
            return _time.time() - self.monitor.status.path.stat().st_mtime < 600
        except (OSError, AttributeError):
            return False

    def start_listening(self):
        """
        Give STARLING ears. Returns (True, "") or (False, "why not").
        Needs start_speech() first, so she can answer, and a microphone.
        """
        if self.listener is not None:
            return True, ""            # already listening: never start a second pair of ears
        from stt.listener import Listener
        from stt.microphone import MicrophoneStream, find_microphone
        from stt.providers import build_stt_providers, choose_stt
        self.stt_providers = build_stt_providers(self.settings)
        stt = choose_stt(self.stt_providers, self.settings)
        if stt is None:
            reasons = "; ".join("%s: %s" % (n, p.available()[1]) for n, p in self.stt_providers.items()
                                if not p.available()[0])
            return False, "No listening provider is available (%s)" % reasons
        device = find_microphone(self.settings.get("stt.microphone", ""))
        runner = self.ensure_commands()
        gate = self.start_push_to_talk()
        self.listener = Listener(self.bus, stt, self.settings, lambda: MicrophoneStream(device), gate=gate)
        if self.ask is not None:
            self.listener.interceptor = self.ask.handle_heard
        if self.speech is not None and self.dialogue is not None:
            self.voice_replies = VoiceReplies(self.bus, self.speech, self.dialogue, self.settings,
                                              commands_active=runner is not None)
            self.voice_replies.attach()
            from personality.manners import Manners
            self.manners = Manners(self.bus, self.speech, self.dialogue, self.settings, mood=self.mood)
            self.manners.attach()
        self.listener.start()
        return True, ""

    def ensure_buttons(self):
        """The reader for keyboard / mouse / joystick (X52) buttons. None if this computer cannot do it."""
        if self.buttons is None:
            try:
                from control.inputs import ButtonReader
                self.buttons = ButtonReader()
            except Exception as error:      # not Windows, or the joystick service is missing
                self.log.warning("Button reading is not available here: %s", error)
                return None
        return self.buttons

    def start_push_to_talk(self):
        """Start watching the push-to-talk button. Returns the PushToTalk object or None."""
        if self.ptt is not None:
            return self.ptt
        reader = self.ensure_buttons()
        if reader is None:
            return None
        from control.ptt import PushToTalk, windows_beep
        self.ptt = PushToTalk(self.settings, reader, beep=windows_beep)
        self.ptt.start()
        return self.ptt

    def ensure_commands(self):
        """Voice commands: understands a sentence and presses your Elite key. Safe to call twice."""
        if self.commands is not None:
            return self.commands
        try:
            from control.binds import BindingBook
            from control.runner import CommandRunner
            from control.sender import KeySender
            from control.learning import VoiceLearning
            from control.matcher import Matcher
            self.learning = VoiceLearning(paths.DATA_DIR / "voice_learning.json",
                                          enabled=lambda: bool(self.settings.get("stt.learning", True)))
            self.commands = CommandRunner(
                self.bus, self.speech, self.dialogue, self.settings, book=BindingBook(), sender=KeySender(),
                matcher=Matcher(learning=self.learning),
                state_provider=lambda: self.state, flavour=self.flavour, echo=self.echo, route=self.ensure_route(),
                macro_hooks=self._macro_hooks(),
                memory=self.memory_recall, smalltalk=self.smalltalk, brain=self.brain)
            # Void Compass overlays: the runner makes its own client from settings voidcompass.port on first use
            self.commands.attach()
            self._connect_auto_plot()
            if self.settings.get("voidcompass.enabled", True):
                self.commands.learn_overlays_in_background(log=self.log)
        except Exception:
            self.log.exception("Voice commands could not start")
            self.commands = None
        return self.commands

    def start_watcher_bridge(self):
        if getattr(self, "watcher", None) is not None:
            return self.watcher
        try:
            from control.voidcompass import DEFAULT_PORT, VoidCompass
            from personality.watcher import WatcherBridge
            try:
                port = int(str(self.settings.get("voidcompass.port", DEFAULT_PORT)).strip())
            except ValueError:
                port = DEFAULT_PORT
            self.watcher = WatcherBridge(self.bus, self.speech, self.dialogue, self.settings, VoidCompass(port=port),
                                         state_provider=lambda: self.state, ask_provider=lambda: self.ask)
            self.watcher.attach()
            self.watcher.start()
        except Exception:
            self.log.exception("The Watcher bridge could not start")
            self.watcher = None
        return self.watcher

    def _macro_hooks(self):
        voice = self.route_voice
        hooks = {"plot_waypoint": voice.prepare_plot} if voice is not None else {}
        hooks["auto_launch"] = self._launch_check
        hooks["show_off"] = self._showoff_check
        return hooks

    def _showoff_check(self):
        """Showing off opens and closes screens, so only from the cockpit and only when it is calm."""
        state = getattr(self, "state", None)
        if state is None or not getattr(state, "status_seen", False):
            return True, ""
        flags = getattr(state, "status_flags", 0) or 0
        flags2 = getattr(state, "status_flags2", 0) or 0
        if flags2 & 1:
            return False, "I can only show off from the cockpit, Commander."
        if flags & ((1 << 25) | (1 << 26)):
            return False, "Not from the SRV or a fighter, Commander."
        if flags & ((1 << 22) | (1 << 23) | (1 << 17) | (1 << 30)):
            return False, "Not now, Commander. We are busy."
        return True, ""

    def _launch_check(self):
        """'Launch' only works while docked, so she never presses Select somewhere else by mistake."""
        state = getattr(self, "state", None)
        if state is None or not getattr(state, "status_seen", False):
            return True, ""                                    # no Status.json yet: trust the commander
        if (getattr(state, "status_flags", 0) or 0) & 1:       # bit 0 = docked
            return True, ""
        return False, "We are not docked, Commander."

    def _connect_auto_plot(self):
        """Lets the route follower start the galaxy map macro by itself (when the setting is on)."""
        follower, runner = self.route_follower, self.commands
        if follower is None or runner is None:
            return
        import threading

        def go():
            threading.Thread(target=lambda: runner.run_text("plot the next waypoint", speak_unknown=False),
                             name="auto-plot", daemon=True).start()
        follower.auto_plot = go

    def memory_text(self):
        """Everything she remembers, as plain text for the Memory page."""
        store = self.memory_store
        if store is None:
            return "Memory is not running."
        stats = store.stats()
        lines = ["Hours together: %.1f   Jumps: %s   Missions: %s   Times destroyed: %s" % (
            stats.get("hours_together", 0) or 0, stats.get("systems_visited", 0), stats.get("missions_completed", 0),
            stats.get("times_destroyed", 0))]
        for memory in store.all(30):
            lines.append("- %s" % memory["summary"])
        if len(lines) == 1:
            lines.append("Nothing remembered yet.")
        return "\n".join(lines)

    def forget_memories(self):
        if self.memory_store is None:
            return "Memory is not running."
        self.memory_store.forget_everything()
        return "Done. She has forgotten everything."

    def ensure_updates(self):
        if getattr(self, "updates", None) is None:
            from core.update_service import UpdateService
            self.updates = UpdateService(self.settings)
        return self.updates

    # ---- the Navigation page buttons (the same things you can say, for when you don't want to talk) ----
    def plot_route_now(self, destination=""):
        """Plot a neutron route. Empty destination = the one saved in settings. Returns a sentence for the screen."""
        voice = self.ensure_route()
        if voice is None:
            return "The neutron plotter could not start. Check the log."
        if not voice.enabled():
            return "The neutron route plotter is switched off in the settings."
        text = (destination or "").strip() or "my destination"
        return voice.plot(text)

    def run_command_now(self, text, delay=4.0, sleep=None, doing="do that"):
        """Runs a voice command (for example 'open the galaxy map') after a short wait, so you can click back into Elite."""
        runner = self.ensure_commands()
        if runner is None:
            return "Voice commands could not start. Check the log."
        import threading
        import time
        wait = sleep or time.sleep

        def go():
            wait(delay)
            runner.run_text(text, speak_unknown=False)
        threading.Thread(target=go, name="run-command", daemon=True).start()
        return "Switch to Elite now. I will %s in %d seconds." % (doing, int(delay))

    def plot_next_now(self, delay=4.0, sleep=None):
        """Runs the galaxy map macro for the next waypoint after a short wait, so you can click back into Elite."""
        return self.run_command_now("plot the next waypoint", delay, sleep, doing="plot the next waypoint")

    def plot_system_by_macro(self, system):
        """Copies a system name to the clipboard and runs the galaxy map macro ('plot the next waypoint') for it.
        No Spansh route is worked out. Returns (ok, reason)."""
        system = str(system or "").strip()
        if not system:
            return False, "I don't have a system name."
        voice = self.ensure_route()
        runner = self.ensure_commands()
        if voice is None or runner is None:
            return False, "voice commands are not running"
        from navigation.route import UNSAFE_BITS
        flags = getattr(self.state, "status_flags", 0) or 0
        if any((flags >> bit) & 1 for bit in UNSAFE_BITS):
            return False, "this is not a safe moment to open the galaxy map"
        voice.set_target(system)
        import threading
        threading.Thread(target=lambda: runner.run_text("plot the next waypoint", speak_unknown=False),
                         name="plot-system", daemon=True).start()
        return True, ""

    def clear_route_now(self):
        voice = self.ensure_route()
        if voice is None:
            return "The neutron plotter could not start."
        return voice.try_handle("cancel the route") or "There was no route."

    def ensure_route(self):
        """The neutron route follower and the 'plot a route' voice command. Safe to call twice."""
        if getattr(self, "route_voice", None) is not None:
            return self.route_voice
        try:
            from navigation.route import RouteFollower
            from navigation.spansh import Spansh
            from navigation.voice import Narrator, RouteVoice
            narrator = Narrator(lambda: self.speech, lambda: self.dialogue, self.settings)
            self.route_follower = RouteFollower(self.bus, self.settings, narrator, lambda: self.state)
            self.route_follower.attach()
            self.route_voice = RouteVoice(self.route_follower, Spansh(), narrator, self.settings, lambda: self.state)
            from navigation.game_target import choose_target
            self.route_voice.plot_macro = lambda system: self.plot_system_by_macro(system)
            self.route_voice.game_target = lambda: choose_target(getattr(self, "journal_folder", None), self.state)
            self.bus.subscribe("NavRoute", self.route_voice.on_nav_route)
            self.bus.subscribe("FSDJump", self.route_voice.on_arrival)
            self.route_voice.journal_folder_provider = lambda: getattr(self, "journal_folder", None)
            self.bus.subscribe("CollectCargo", self.route_voice.on_cargo)
        except Exception:
            self.log.exception("The neutron plotter could not start")
            self.route_voice = None
        return self.route_voice

    def ensure_bio_distance(self):
        """Beep and speak when you have walked far enough from a biological sample. Needs the monitor (Status.json)."""
        try:
            from journal.bio_distance import BioDistance
            from navigation.voice import Narrator
            narrator = Narrator(lambda: self.speech, lambda: self.dialogue, self.settings)
            self.bio_distance = BioDistance(self.bus, narrator, self.settings, lambda: self.state)
            self.bio_distance.attach()
            self.monitor.status.listeners.append(self.bio_distance.check)
        except Exception:
            self.log.exception("The biology distance alert could not start")
            self.bio_distance = None

    def ensure_auto_shields(self):
        """Raises the suit shields when you draw a weapon or take damage on foot (dashboard setting, off by default)."""
        try:
            from control.auto_shields import AutoShields
            from control.binds import BindingBook
            from control.sender import KeySender
            book, sender = BindingBook(), KeySender()
            self.auto_shields = AutoShields(self.settings, book, sender)
            self.monitor.status.listeners.append(self.auto_shields.check)
            for name in ("FactionKillBond", "Bounty"):              # signs of a fight on foot
                self.bus.subscribe(name, self.auto_shields.on_combat_event)
            from control.onfoot_care import OnFootCare
            from navigation.voice import Narrator
            narrator = Narrator(lambda: self.speech, lambda: self.dialogue, self.settings)
            self.onfoot_care = OnFootCare(self.settings, book, sender, narrator, lambda: self.journal_folder)
            self.monitor.status.listeners.append(self.onfoot_care.check)
        except Exception:
            self.log.exception("Auto shields could not start")
            self.auto_shields = None
        self.onfoot_care = None

    def ensure_limpet_reminder(self):
        """Reminds you to buy limpets when you dock in a mining ship. Safe to call twice."""
        if getattr(self, "limpet_reminder", None) is not None:
            return self.limpet_reminder
        try:
            from control.limpet_reminder import LimpetReminder
            from navigation.voice import Narrator
            narrator = Narrator(lambda: self.speech, lambda: self.dialogue, self.settings)
            self.limpet_reminder = LimpetReminder(self.bus, self.settings, narrator, lambda: self.state,
                                                  lambda: self.journal_folder)
            self.limpet_reminder.attach()
        except Exception:
            self.log.exception("The limpet reminder could not start")
            self.limpet_reminder = None
        return self.limpet_reminder

    def ensure_regions(self):
        """Announces the galaxy region you jump into (and the first time you are in it). Safe to call twice."""
        if getattr(self, "region_tracker", None) is not None:
            return self.region_tracker
        try:
            from navigation.regions import RegionTracker
            from navigation.voice import Narrator
            narrator = Narrator(lambda: self.speech, lambda: self.dialogue, self.settings)
            self.region_tracker = RegionTracker(self.bus, narrator, self.settings, lambda: self.state,
                                                journal_folder=self.journal_folder)
            self.region_tracker.attach()
        except Exception:
            self.log.exception("The region announcer could not start")
            self.region_tracker = None
        return self.region_tracker

    def ensure_autohonk(self):
        """Auto honk on arrival. Always attached; the dashboard setting decides whether it does anything."""
        if self.autohonk is not None:
            return self.autohonk
        try:
            from control.autohonk import AutoHonk
            from control.binds import BindingBook
            from control.sender import KeySender
            self.autohonk = AutoHonk(self.bus, self.settings, BindingBook(), KeySender(),
                                     lambda: self.state, speech=self.speech)
            self.autohonk.attach()
        except Exception:
            self.log.exception("Auto honk could not start")
            self.autohonk = None
        return self.autohonk

    def on_nomad_docked(self, _event=None):
        """The Nomad is back aboard: put the hardpoints away (only if they are out, and only if the setting is on)."""
        if not self.settings.get("nomad.stow_hardpoints", True):
            return
        runner = self.ensure_commands()
        if runner is None:
            return
        import threading
        import time

        def go():
            time.sleep(2.5)                                   # let the game finish switching you back to the ship
            if (getattr(self.state, "status_flags", 0) or 0) & (1 << 6):      # bit 6 = hardpoints deployed
                runner.run_text("weapons away", speak_unknown=False)
        threading.Thread(target=go, name="nomad-stow", daemon=True).start()

    def _say_line(self, key, fields=None):
        """Speak a line of dialogue in her current mood, filling in {gaps} (used by the favourite ship)."""
        if self.speech is None or self.dialogue is None or not self.settings.get("speech.enabled", True):
            return False
        from core.identity import personalise
        from personality.mood_engine import effective_mood
        info = self.settings.get("personality.style", "personality") == "info"
        line = self.dialogue.pick(key, "" if info else effective_mood(self.settings), bool(self.settings.get("speech.allow_mature", False)), False)
        if line is None:
            return False

        class _Quiet(dict):
            def __missing__(self, k):
                return ""
        try:
            text = line.text.format_map(_Quiet(fields or {}))
        except (ValueError, IndexError):
            text = line.text
        return bool(self.speech.say(text=personalise(text, self.settings), priority="normal", event_name="personality.favourite"))

    def honk_now(self):
        """The dashboard's test button. Returns a sentence for the screen."""
        honk = self.ensure_autohonk()
        if honk is None:
            return "Auto honk could not start. Check the log."
        return honk.test_now()

    def ensure_combat_assist(self):
        """Auto pips, shield cells and heat sinks in a fight. Always attached; the dashboard toggles decide."""
        if self.combat_assist is not None:
            return self.combat_assist
        reader = self.ensure_buttons()
        if reader is None:
            return None
        try:
            from control.binds import BindingBook
            from control.combat_assist import CombatAssist
            from control.sender import KeySender
            self.combat_assist = CombatAssist(self.bus, self.settings, BindingBook(), KeySender(), reader,
                                              lambda: self.state, speech=self.speech, dialogue=self.dialogue)
            self.combat_assist.attach()
        except Exception:
            self.log.exception("Combat assist could not start")
            self.combat_assist = None
        return self.combat_assist

    def start_monitor(self):
        """Start watching the real game. Returns the journal folder, or None."""
        self.journal_folder = find_journal_folder(self.settings.get("journal.folder", ""))
        if self.journal_folder is None:
            return None
        self.ensure_autohonk()
        self.bus.subscribe("NomadDocked", self.on_nomad_docked)
        self.ensure_combat_assist()
        self.ensure_limpet_reminder()
        self.ensure_route()
        self.ensure_regions()
        poll = self.settings.get("journal.poll_seconds", 1.0)
        self.monitor = JournalMonitor(self.journal_folder, self.processor, self.bus, poll)
        self.ensure_bio_distance()
        self.ensure_auto_shields()
        self.monitor.start()
        return self.journal_folder

    # ---- shutting down ----
    def stop(self):
        if self.chitchat is not None:
            self.chitchat.stop()
            self.chitchat = None
        if self.warmer is not None:
            self.warmer.stop()
            self.warmer = None
        if getattr(self, "bio_distance", None) is not None:
            self.bio_distance.detach()
            self.bio_distance = None
        if getattr(self, "region_tracker", None) is not None:
            self.region_tracker.detach()
            self.region_tracker = None
        if getattr(self, "message_reader", None) is not None:
            self.message_reader.detach()
            self.message_reader = None
        if getattr(self, "watcher", None) is not None:
            self.watcher.detach()
            self.watcher = None
        if self.mood is not None:
            self.mood.stop_timer()
            self.mood.save()
        if self.listener is not None:
            self.listener.stop()
            self.listener = None
        if self.combat_assist is not None:
            self.combat_assist.detach()
            self.combat_assist = None
        if self.ptt is not None:
            self.ptt.stop()
            self.ptt = None
        if self.speech is not None:
            self.speech.stop()
            self.speech = None
        if self.monitor is not None:
            self.monitor.stop()
            self.monitor = None
            self._save_ignored_report()
        if self.database is None:
            return
        try:
            self.bus.publish("app.stopping")
            if self.event_logger is not None:
                self.event_logger.stop()          # write the last events before the database closes
                self.event_logger = None
            if self.session_id is not None:
                self.database.execute(
                    "UPDATE sessions SET ended_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (self.session_id,),
                )
            self.log.info("%s shut down cleanly.", APP_NAME)
        finally:
            self.database.close()
            self.database = None
            shutdown_logging()

    # ---- helpers ----
    def _save_ignored_report(self):
        """Write logs/ignored_events.txt: journal events STARLING doesn't know yet."""
        try:
            lines = self.processor.ignored_report()
            if not lines:
                return
            target = (self._logs_dir or paths.LOGS_DIR) / "ignored_events.txt"
            text = "Journal events STARLING ignored this session (name: count)\n\n" + "\n".join(lines) + "\n"
            target.write_text(text, encoding="utf-8")
        except OSError:
            self.log.exception("Could not save the ignored events report")

    def _log_event(self, event):
        self.log.debug("event %s [%s] %s", event.name, event.priority, event.data)

    def status_report(self):
        """A short, friendly report shown when STARLING starts."""
        relationship = self.database.fetch_one("SELECT * FROM relationship WHERE id = 1")
        critical = [n for n, i in self.event_config.items() if i["priority"] == "critical"]
        enabled = [n for n, i in self.event_config.items() if i["enabled"]]
        return [
            "",
            "==============================",
            "  %s is online." % APP_NAME,
            "==============================",
            "Version:          %s" % APP_VERSION,
            "Python:           %s" % sys.version.split()[0],
            "Project folder:   %s" % paths.ROOT,
            "Database:         %s (design version %d, %d tables)"
            % (paths.DATABASE_FILE.name, self.database.schema_version(), len(self.database.table_names())),
            "Relationship:     trust %d, patience %d, affection %d, respect %d"
            % (relationship["trust"], relationship["patience"], relationship["affection"], relationship["respect"]),
            "Events:           %d known, %d enabled, %d critical (always on)"
            % (len(self.event_config), len(enabled), len(critical)),
            "Event files:      %d loaded" % len(self.registry),
            "Log files:        %s" % paths.LOGS_DIR,
            "",
        ]
