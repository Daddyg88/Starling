"""
The CommandRunner: hears a sentence, works out the command, presses YOUR key, and tells you what she did.

    "Starling, lower the landing gear"
        -> matcher        : gear, intent "on"
        -> status check   : gear already down?  then just say so (never toggles it back UP by mistake)
        -> binding book   : your key for LandingGearToggle is Key_L
        -> sender         : press L (only if Elite Dangerous is the window you are looking at)
        -> speech         : "Lowering the landing gear, Commander."

Every outcome has a plain status word so the dashboard and the tests can see what happened:
    done, already, unbound, joystick_only, unknown_key, no_file, not_in_file,
    game_not_active, not_windows, failed, unknown, disabled, duplicate
"""

import time
from dataclasses import dataclass
from typing import List, Optional

from control import easter_eggs
from control import binds, sender as sender_module
from control.confirm import Confirmer
from control.matcher import Matcher, normalise
from core.identity import personalise
from core.logger import get_logger
from personality.mood_engine import effective_mood

log = get_logger("commands")

DUPLICATE_SECONDS = 2.0          # the same command heard twice this fast is one command
GAP_BETWEEN_COMMANDS = 0.35      # pause between "lower the gear and open the map"

LINE_FOR_STATUS = {
    "done": "CommandDone",
    "already": "CommandAlready",
    "unbound": "CommandUnbound",
    "joystick_only": "CommandJoystickOnly",
    "unknown_key": "CommandUnknownKey",
    "no_file": "CommandNoBinds",
    "not_in_file": "CommandNoBinds",
    "game_not_active": "CommandNotInGame",
    "not_windows": "CommandFailed",
    "failed": "CommandFailed",
    "no_button": "CommandNoButton",
    "no_nomad": "CommandNoNomad",
    "no_slf": "CommandNoFighter",
    "no_srv": "CommandNoSrv",
    "cannot_landed": "CommandCannotLanded",
    "cannot_high30": "CommandCannotHigh30",
    "cannot_slf_low": "CommandCannotFighterLow",
    "cannot_close": "CommandCannotTooClose",
    "cannot_key": "CommandCannotKey",
    "cannot_other": "CommandCannotDeploy",
    "no_target": "CommandNoTarget",
    "no_scan": "CommandNotScanned",
    "no_subsystem": "CommandNoSubsystem",
    "sub_unread": "CommandSubUnread",
    "unknown": "CommandUnknown",
    "vc_offline": "CommandVoidOffline",
    "vc_forbidden": "CommandVoidForbidden",
    "vc_conflict": "CommandVoidOther",
    "vc_missing": "CommandVoidOther",
    "vc_failed": "CommandVoidOther",
    "vc_disabled": "CommandVoidOther",
}
SEND_FAILURE_STATUS = {
    sender_module.NOT_WINDOWS: "not_windows",
    sender_module.GAME_NOT_ACTIVE: "game_not_active",
    sender_module.UNKNOWN_KEY: "unknown_key",
    sender_module.FAILED: "failed",
}


LITERAL_KEYS = {"paste": binds.Keystroke("V", ("LeftControl",)), "enter": binds.Keystroke("Enter")}


@dataclass
class Outcome:
    status: str
    text: str = ""
    command: object = None
    intent: str = ""
    keys: str = ""             # e.g. "L" or "Left Shift + F"
    detail: str = ""           # the sentence she would say (without personality)


def speak_ok(runner):
    return not getattr(runner, "auto_run", False)       # sentences she makes up herself (the route plotter) are not your misses


class CommandRunner:
    def __init__(self, bus, speech, dialogue, settings, book=None, sender=None, state_provider=None,
                 matcher=None, flavour=None, clock=time.monotonic, sleep=time.sleep, echo=None, voidcompass=None, route=None, macro_hooks=None, memory=None, smalltalk=None, brain=None):
        self.bus = bus
        self.speech = speech
        self.dialogue = dialogue
        self.settings = settings
        self.book = book if book is not None else binds.BindingBook()
        self.sender = sender if sender is not None else sender_module.KeySender()
        self.state_provider = state_provider or (lambda: None)
        self.matcher = matcher or Matcher()
        self.flavour = flavour
        self._docking_seen = []
        self.echo = echo                 # control/echo.py: tells the event speaker not to repeat what she just did
        self.macro_hooks = macro_hooks or {}     # command id -> function run before its macro; returns (ok, sentence)
        self.brain = brain               # personality/brain.py: answers anything that is not a command
        self.smalltalk = smalltalk       # personality/smalltalk.py: "how are you?", "tell me a joke"
        self.memory = memory             # memory/recall.py: "what do you remember"
        self._tab_memory = {"left": {}, "right": {}}   # where she last saw each tab of each panel (a faster tab walk next time)
        self._tab_height = {}                          # the height of each panel's tab bar on screen, once she has seen it
        self.panel_reader = None         # a function that returns a screenshot (tests give a pretend one); None = the real screen
        self.extra_helpers = []          # more voice helpers (the biology overlay) that answer before anything else
        self.route = route               # navigation/voice.py: 'plot a neutron route to Colonia'
        self.voidcompass = voidcompass   # control/voidcompass.py (made on first use if not given)
        self.clock = clock
        self.sleep = sleep
        self.journal_boost = None               # (seconds) -> reads the journal ten times a second for a while (set by the app)
        self.confirmer = Confirmer(clock)       # "did you mean...?"
        self.trainer = None                     # stt/training.py: 'teach me your voice' (set by the app)
        self._last = {}
        self._clash_warned = set()
        self.last_outcomes: List[Outcome] = []

    # ---- wiring ----
    def attach(self):
        self.bus.subscribe("voice.heard", self.on_heard)
        for name in ("DockingRequested", "DockingGranted", "DockingDenied"):
            self.bus.subscribe(name, self._on_docking_event)

    def _on_docking_event(self, event):
        self._docking_seen.append(getattr(event, "name", None) or str(event))

    def detach(self):
        self.bus.unsubscribe("voice.heard", self.on_heard)
        for name in ("DockingRequested", "DockingGranted", "DockingDenied"):
            self.bus.unsubscribe(name, self._on_docking_event)

    def learn_overlays(self):
        """Ask Void Compass what overlays it has and add voice commands for any we don't know. Returns the labels added.
        Raises VoidError if Void Compass can't be reached (the caller decides whether to try again)."""
        from control.catalog import overlay_command
        from control.vc_overlays import discover
        rows = self._void().overlays().get("overlays", [])
        added = []
        for spec in discover(rows):
            if self.matcher.add(overlay_command(*spec)):
                added.append(spec[1])
        return added

    def learn_overlays_in_background(self, tries=6, wait=60, log=None):
        """Void Compass may start after Starling, so try a few times, then give up quietly."""
        import threading

        def work():
            for _ in range(tries):
                try:
                    added = self.learn_overlays()
                    if added and log:
                        log.info("New Void Compass overlays you can now ask for: %s", ", ".join(added))
                    return
                except Exception:
                    self.sleep(wait)
        thread = threading.Thread(target=work, name="vc-overlays", daemon=True)
        thread.start()
        return thread

    # ---- hearing ----
    def addressed(self, data):
        if data.get("wake"):
            return True
        if data.get("ptt") and self.settings.get("ptt.skip_wake", True):
            return True
        return not self.settings.get("stt.require_wake", True)

    def on_heard(self, event):
        if not self.settings.get("commands.enabled", True):
            return
        data = event.data
        if self.trainer is not None and self.trainer.active():      # voice training: every sentence is an answer, no name needed
            try:
                if self.trainer.hear((data.get("command") if data.get("wake") else data.get("text")) or ""):
                    return
            except Exception:
                log.exception("Voice training failed")
        if self.confirmer.active():                 # she just asked "did you mean...?": a yes or a no needs no wake word
            answer = self.confirmer.answer((data.get("command") if data.get("wake") else data.get("text")) or "")
            if answer:
                self._confirm_answer(answer)
                return
        if not self.addressed(data):
            self._chat_window(data)
            return
        text = data.get("command") if data.get("wake") else data.get("text")
        if not normalise(text or ""):
            return                      # she only heard her name: VoiceReplies says "Yes?"
        from personality.manners import only_thanks
        if only_thanks(text):
            return                      # a plain "thank you" is not a command; Manners answers it
        deliberate = bool(data.get("wake") or data.get("ptt"))
        self.run_text(text, speak_unknown=deliberate)

    def _confirm_answer(self, answer):
        """You said yes or no to 'did you mean...?'."""
        pending = self.confirmer.take()
        if pending is None:
            return
        match, heard, _expires = pending
        if answer == "no":
            self.confirmer.refuse(normalise(heard), match.phrase)
            self._speak("CommandConfirmNo", {}, fallback="Okay, never mind.")
            return
        outcome = self.execute(match, heard)
        learning = getattr(self.matcher, "learning", None)
        if learning is not None and not match.command.strict and outcome.status in ("done", "already"):
            from control.learning import PROMOTE_AFTER
            for _ in range(PROMOTE_AFTER):                      # you confirmed it: that is how YOU say it, so she learns it at once
                learning.note(normalise(heard), match.phrase)
        self._finish([outcome], True, heard)

    def _chat_window(self, data):
        """She just asked a question: an answer without her name is chat, never a command (free chat window)."""
        brain = self.brain
        if brain is None or data.get("wake") or not brain.in_conversation():
            return
        text = data.get("text") or ""
        if not text.strip() or self.matcher.match(text) is not None:
            return                      # a real command needs her name; this one is ignored
        try:
            brain.chat_window_turn(text)
        except Exception:
            log.exception("The chat window failed")

    # ---- doing ----
    def run_text(self, text, speak_unknown=True, speak=True, auto=False):
        """Understand and carry out a sentence. Returns the list of Outcomes.
        auto=True is for things she does by herself (the hands-free route plotting): she only speaks if it goes wrong."""
        started = self.clock()
        self.auto_run = bool(auto)
        try:
            outcomes = self._run_text(text, speak_unknown, speak)
        finally:
            self.auto_run = False
        took = self.clock() - started
        (log.info if took > 1.0 else log.debug)("Command %r took %.2f s", text, took)
        return outcomes

    def _run_text(self, text, speak_unknown=True, speak=True):
        secret = easter_eggs.rewrite(text)
        if secret is not None:
            text = secret                                  # a private phrase: carry out the ordinary command it stands for
        for name, helper in self.voice_helpers():       # spoken questions and the route plotter answer for themselves
            try:
                handled = helper.try_handle(text)
            except Exception:
                log.exception("The voice helper %s failed", name)
                handled = None
            if handled is not None:
                log.debug("%r was answered by the %s helper", text, name)
                outcome = Outcome("route", text, None, "press", detail=handled)
                self._finish([outcome], False, text)
                return [outcome]
        matches = []
        single = None if self._brain_owns(text) else self.matcher.match(text)
        if single is not None:
            matches = [single]
        else:
            matches = self.matcher.split(text)
        if not matches and self.brain is not None:
            try:
                answer = self.brain.try_handle(text, deliberate=speak_unknown)
            except Exception:
                log.exception("Her brain failed")
                answer = None
            if answer is not None:
                outcome = Outcome("route", text, None, "press", detail=answer)
                self._finish([outcome], False, text)
                return [outcome]
        if not matches and speak and speak_unknown and self.settings.get("commands.ask_guess", True):
            suggestion = self.matcher.suggest(text)
            if (suggestion is not None and not self.confirmer.is_refused(normalise(text), suggestion.phrase)
                    and suggestion.command.id not in (self.settings.get("commands.disabled", []) or [])):
                self.confirmer.ask(suggestion, text)
                self._note_miss(text)
                question = "Did you mean %s?" % suggestion.phrase
                self._speak("CommandConfirm", {"phrase": suggestion.phrase}, fallback=question)
                outcome = Outcome("asked", text, suggestion.command, suggestion.intent, detail=question)
                self._finish([outcome], False, text)
                return [outcome]
        if not matches:
            self._note_miss(text)
            outcome = Outcome("unknown", text=text, detail="I didn't recognise that command.")
            self._finish([outcome], speak and speak_unknown, text)
            return [outcome]
        outcomes = []
        for index, match in enumerate(matches):
            if index:
                self.sleep(GAP_BETWEEN_COMMANDS)
            outcomes.append(self.execute(match, text))
        self._finish(outcomes, speak, text)
        return outcomes

    def _note_miss(self, text):
        learning = getattr(self.matcher, "learning", None)
        if learning is not None and speak_ok(self):
            try:
                learning.note_miss(normalise(text), self.clock())
            except Exception:
                log.exception("Could not note a missed sentence")

    def voice_helpers(self):
        """[(name, helper)] in the order they get to answer a spoken sentence, before the command list and her brain.
        Order: the extra helpers (added with add_helper), small talk, memory questions, the route plotter."""
        found = [(type(h).__name__, h) for h in self.extra_helpers if h is not None]
        for name, helper in (("SmallTalk", self.smalltalk), ("Memory", self.memory), ("Route", self.route)):
            if helper is not None:
                found.append((type(helper).__name__ or name, helper))
        return found

    def add_helper(self, helper, first=False):
        """Plug in a new voice helper (an object with try_handle(text) that returns None when it is not for it).
        first=True lets it answer before the others."""
        if first:
            self.extra_helpers.insert(0, helper)
        else:
            self.extra_helpers.append(helper)

    def _brain_owns(self, text):
        """A sentence that is NOT an exact command but IS one of her chat intents goes to her brain, not to a guessed command.
        (Found in a log review: 'tell me more' was being matched, by sound, to the on-foot 'tool mode' key.)"""
        brain = self.brain
        if brain is None or not hasattr(brain, "recognises"):
            return False
        clean = normalise(text)
        if not clean or clean in self.matcher.index:
            return False
        learning = getattr(self.matcher, "learning", None)
        try:
            if learning is not None and learning.learned(clean) in self.matcher.index:
                return False
            return bool(brain.recognises(text))
        except Exception:
            log.exception("The brain check failed")
            return False

    def current_state(self, command):
        """True / False if Status.json says whether it is on right now, None if unknown."""
        if command.flag is None:
            return None
        state = self.state_provider()
        if state is None or not getattr(state, "status_seen", False):
            return None
        field, bit, inverted = command.flag
        value = state.status_flags if field == "Flags" else state.status_flags2
        on = bool(value & (1 << bit))
        return (not on) if inverted else on

    def execute(self, match, text=""):
        command, intent = match.command, match.intent
        if command.id in (self.settings.get("commands.disabled", []) or []):
            return Outcome("disabled", text, command, intent, detail="That command is switched off.")
        now = self.clock()
        key = (command.id, intent)
        if now - self._last.get(key, -99) < DUPLICATE_SECONDS:
            return Outcome("duplicate", text, command, intent, detail="Heard that twice; pressed once.")
        current = self.current_state(command)
        if intent in ("on", "off") and current is not None and current == (intent == "on"):
            return Outcome("already", text, command, intent,
                           detail="%s is already %s." % (command.label[0].upper() + command.label[1:],
                                                          command.words[0 if intent == "on" else 1]))
        if command.service:
            return self._run_service(command, intent, text, now, key)
        if command.macro:
            return self._run_macro(command, intent, text, now, key)
        action, doing_text = command.action, None
        stroke, why = self.book.lookup(action)
        if stroke is None:
            status = {binds.UNBOUND: "unbound", binds.JOYSTICK_ONLY: "joystick_only",
                      binds.UNKNOWN_KEY: "unknown_key", binds.NO_FILE: "no_file",
                      binds.NOT_IN_FILE: "not_in_file"}.get(why, "failed")
            return Outcome(status, text, command, intent, detail=self._explain(status, command))
        self.sender.require_game = bool(self.settings.get("commands.require_game_focus", True))
        if self.echo is not None:
            self.echo.expect(command.echo)         # before pressing: the game's reply can be very quick
        problem = self.sender.send(stroke)
        if problem:
            if self.echo is not None:
                self.echo.cancel(command.echo)
            status = SEND_FAILURE_STATUS.get(problem, "failed")
            return Outcome(status, text, command, intent, detail=self._explain(status, command))
        self._last[key] = now
        return Outcome("done", text, command, intent, keys=stroke.describe(),
                       detail=(doing_text or command.do_text(intent)) + ".")

    # ---- other apps (Void Compass overlays) ----
    def _void(self):
        if self.voidcompass is None:
            from control.voidcompass import DEFAULT_PORT, VoidCompass
            try:
                port = int(str(self.settings.get("voidcompass.port", DEFAULT_PORT)).strip())
            except ValueError:
                port = DEFAULT_PORT
            self.voidcompass = VoidCompass(port=port if 1 <= port <= 65535 else DEFAULT_PORT)
        return self.voidcompass

    def _run_service(self, command, intent, text, now, key):
        from control.vc_overlays import HIDE_ALL, SHOW_ALL
        from control.voidcompass import VoidError
        if command.service[0] != "voidcompass" or not self.settings.get("voidcompass.enabled", True):
            return Outcome("vc_disabled", text, command, intent, detail="Void Compass control is switched off in my settings.")
        target = command.service[1]
        try:
            client = self._void()
            if target in (HIDE_ALL, SHOW_ALL):
                client.hide_all(target == HIDE_ALL)
                self._last[key] = now
                return Outcome("done", text, command, intent, keys="Void Compass",
                               detail=command.do_text(intent) + ".")
            answer = client.overlays()
            row = next((o for o in answer.get("overlays", []) if o.get("id") == target), None)
            if row is None:
                return Outcome("vc_missing", text, command, intent,
                               detail="This version of Void Compass doesn't have %s." % command.label)
            on = bool(row.get("enabled"))
            want = (not on) if intent == "toggle" else (intent == "on")
            name = command.label
            if want == on:
                return Outcome("already", text, command, intent,
                               detail="%s is already %s." % (name[0].upper() + name[1:], "on" if on else "off"))
            client.set_enabled(target, want)
        except VoidError as error:
            return Outcome("vc_" + (error.kind if error.kind in ("offline", "forbidden", "conflict", "missing") else "failed"),
                           text, command, intent, detail=self._void_explain(error))
        self._last[key] = now
        detail = ("Switching %s %s" % ("on" if want else "off", name))
        if want and answer.get("hidden"):
            detail += ", but all overlays are hidden, so say show overlays to see it"
        return Outcome("done", text, command, intent, keys="Void Compass", detail=detail + ".")

    @staticmethod
    def _void_explain(error):
        return {
            "offline": "I can't reach Void Compass. Check it is running and its Local API is switched on in Settings, Integrations.",
            "forbidden": "Void Compass is set to read only. Switch on Allow control in its Local API settings.",
        }.get(error.kind, error.message or "Void Compass wouldn't do that.")

    def macro_steps(self, command):
        """The steps for a macro command: yours from settings.json if you wrote some, else the built-in ones."""
        custom = (self.settings.get("macros", {}) or {}).get(command.id)
        return custom if isinstance(custom, list) and custom else list(command.macro)

    def _gui_focus(self):
        state = self.state_provider()
        return getattr(state, "gui_focus", "?") if state is not None and getattr(state, "status_seen", False) else "?"

    def _check_docking_later(self):
        """Four seconds after the docking macro, writes to the log whether the game really answered (journal DockingRequested)."""
        import threading

        def check():
            if self._docking_seen:
                log.info("Docking request: the game answered (%s).", ", ".join(self._docking_seen))
            else:
                log.warning("Docking request: the game did NOT answer within 4 s (no DockingRequested in the journal). "
                            "The keys were sent, so one of them was not taken: see the macro trace line above.")
        timer = threading.Timer(4.0, check)
        timer.daemon = True
        timer.start()

    def galaxy_map_open(self):
        """True while Status.json says the galaxy map is the screen you are looking at (GuiFocus 6)."""
        state = self.state_provider()
        return bool(state is not None and getattr(state, "status_seen", False) and getattr(state, "gui_focus", 0) == 6)

    def _run_macro(self, command, intent, text, now, key):
        from control.macros import GAP_SECONDS, actions_in, parse_macro
        try:
            steps = parse_macro(self.macro_steps(command))
        except ValueError as error:
            return Outcome("failed", text, command, intent, detail="The %s macro in your settings is wrong: %s" % (command.label, error))
        if command.id == "plot_waypoint" and self.galaxy_map_open() and steps and steps[0] == ("press", "GalaxyMapOpen", 1):
            steps = steps[1:]                                    # the map is already open: pressing its key would CLOSE it
            if steps and steps[0][0] == "wait":
                steps = [("wait", 0.4)] + steps[1:]
        hook = self.macro_hooks.get(command.id)
        if hook is not None:
            ok, sentence = hook()
            if not ok:
                return Outcome("failed", text, command, intent, detail=sentence)
        strokes = {}
        for action in actions_in(steps):
            stroke, why = self.book.lookup(action)
            if stroke is None:
                status = {binds.UNBOUND: "unbound", binds.JOYSTICK_ONLY: "joystick_only", binds.UNKNOWN_KEY: "unknown_key",
                          binds.NO_FILE: "no_file", binds.NOT_IN_FILE: "not_in_file"}.get(why, "failed")
                detail = self._explain(status, command)
                if status in ("unbound", "joystick_only", "not_in_file"):
                    detail = "For %s I need a keyboard key for %s in your Elite controls." % (command.label, action)
                return Outcome(status, text, command, intent, detail=detail)
            strokes[action] = stroke
        self._key_clashes(strokes)               # logged only: she no longer talks about it
        self.sender.require_game = bool(self.settings.get("commands.require_game_focus", True))
        try:
            self.sender.hold_seconds = max(0.03, min(float(self.settings.get("commands.key_hold", 0.06)), 0.5))
        except (TypeError, ValueError, AttributeError):
            pass
        trace = []                               # what the game was showing after each wait (GuiFocus from Status.json)
        self._docking_seen = []
        quiet = ("GalaxyMapOpened", "GalaxyMapClosed", "ScreenClosed") if command.id == "plot_waypoint" else ()
        if command.id == "show_off":                      # she opens and closes these herself: no "opening the galaxy map" chatter
            quiet = ("GalaxyMapOpened", "GalaxyMapClosed", "ScreenClosed", "InternalPanelOpened", "ExternalPanelOpened",
                     "CommsPanelOpened", "RolePanelOpened")
        if getattr(self, "auto_run", False) and command.id == "plot_waypoint" and self.echo is not None:
            self.echo.mute(("NavRoute",), 40)                # she set the course herself: no "Plotting a route" on top of the route lines
        if quiet and self.echo is not None:
            self.echo.mute(quiet, 300 if command.id == "show_off" else 60)           # she opens and closes the map herself: no "opening / closing the galaxy map"
        pressed = []
        self._no_button = False
        self._role_keys_logged = set()
        self._role_status = None                     # "no_nomad", "cannot_landed"... when a role-panel pick could not be done
        self.macro_spoke = False
        for step in steps:
            if step[0] == "wait":
                self.sleep(step[1])
                trace.append("%s>gui%s" % (pressed[-1] if pressed else "-", self._gui_focus()))
                continue
            if step[0] in ("say", "talk") and (self._no_button or self._role_status):
                continue                                       # she could not find the button: do not talk as if all is well
            if step[0] == "say":
                self.macro_spoke = True
                self._speak(step[1], {}, fallback="")
                continue
            if step[0] == "talk":
                self.macro_spoke = True
                self._speak(step[1], {}, fallback="", plain=True)       # queued: the next steps run while she talks
                continue
            if step[0] == "finish":
                waiter = getattr(self.speech, "wait_until_idle", None)
                if waiter is not None:
                    waiter(60.0)
                continue
            if step[0] == "leave":
                gui = self._gui_focus()
                if gui == step[2] or gui == "?":
                    problem = self.sender.send(strokes[step[1]], hold=0.15)
                    pressed.append(step[1])
                    if problem:
                        status = SEND_FAILURE_STATUS.get(problem, "failed")
                        return Outcome(status, text, command, intent, detail=self._explain(status, command))
                    self.sleep(GAP_SECONDS)
                continue
            if step[0] == "stopclosed":
                if self._gui_focus() == 0:
                    trace.append("closed>stop")
                    break
                continue
            if step[0] == "selectbutton":
                problem = self._select_button(strokes, pressed, trace)
                if problem == "no_button":
                    self._no_button = True               # carry on tidying up (back to Navigation, close the panel), then report
                elif problem:
                    status = SEND_FAILURE_STATUS.get(problem, "failed")
                    return Outcome(status, text, command, intent, detail=self._explain(status, command))
                continue
            if step[0] == "openleft":
                problem = self._open_left_panel(strokes, pressed, trace)
                if problem:
                    status = SEND_FAILURE_STATUS.get(problem, "failed")
                    return Outcome(status, text, command, intent, detail=self._explain(status, command))
                continue
            if step[0] == "closepanels":
                gui = self._gui_focus()
                trace.append("close>gui%s" % gui)
                for _ in range(4):
                    if gui not in (1, 2, 3, 4, "?"):
                        break                                  # closed (0), or a map / services screen that is none of her business
                    problem = self.sender.send(strokes["UI_Back"], hold=0.15)
                    pressed.append("UI_Back")
                    if problem:
                        status = SEND_FAILURE_STATUS.get(problem, "failed")
                        return Outcome(status, text, command, intent, detail=self._explain(status, command))
                    self.sleep(0.45)
                    gui = self._gui_focus()
                    if gui == "?":
                        break                                  # Status.json unreadable: one press, as a plain Back would
                continue
            if step[0] == "subsystem":
                if self._role_status or self._no_button:
                    continue
                problem = self._subsystem_step(step[1], strokes, pressed, trace)
                if problem:
                    status = SEND_FAILURE_STATUS.get(problem, "failed")
                    return Outcome(status, text, command, intent, detail=self._explain(status, command))
                continue
            if step[0] == "openrole":
                problem = self._open_left_panel(strokes, pressed, trace, "FocusRadarPanel", 4)
                if problem:
                    status = SEND_FAILURE_STATUS.get(problem, "failed")
                    return Outcome(status, text, command, intent, detail=self._explain(status, command))
                continue
            if step[0] in ("roletab", "rolepick"):
                if self._role_status or self._no_button:
                    continue                                   # an earlier step already said no: just tidy up
                problem = self._role_step(step, strokes, pressed, trace)
                if problem:
                    status = SEND_FAILURE_STATUS.get(problem, "failed")
                    return Outcome(status, text, command, intent, detail=self._explain(status, command))
                continue
            if step[0] == "openright":
                problem = self._open_left_panel(strokes, pressed, trace, "FocusRightPanel", 1)
                if problem:
                    status = SEND_FAILURE_STATUS.get(problem, "failed")
                    return Outcome(status, text, command, intent, detail=self._explain(status, command))
                continue
            if step[0] == "tab":
                panel = step[3] if len(step) > 3 else "left"
                problem = self._go_to_tab(step[1], strokes, pressed, trace, step[2] if len(step) > 2 else 0, panel)
                if problem == "no_screen":                     # the right panel cannot be counted blind: stop and say so
                    return Outcome("no_button", text, command, intent, detail=self._explain("no_button", command))
                if problem:
                    status = SEND_FAILURE_STATUS.get(problem, "failed")
                    return Outcome(status, text, command, intent, detail=self._explain(status, command))
                continue
            if step[0] == "ensure":
                if self._gui_focus() == 0:                       # only when Status.json clearly says NO screen is open
                    problem = self.sender.send(strokes[step[1]], hold=0.15)
                    pressed.append(step[1])
                    if problem:
                        status = SEND_FAILURE_STATUS.get(problem, "failed")
                        return Outcome(status, text, command, intent, detail=self._explain(status, command))
                    self.sleep(1.6)
                    trace.append("reopened>gui%s" % self._gui_focus())
                continue
            if step[0] in ("hold", "literal"):
                if step[0] == "hold":
                    problem = self.sender.send(strokes[step[1]], hold=step[2])
                    pressed.append(step[1])
                else:
                    problem = self.sender.send(LITERAL_KEYS[step[1]])
                if problem:
                    status = SEND_FAILURE_STATUS.get(problem, "failed")
                    return Outcome(status, text, command, intent, detail=self._explain(status, command))
                self.sleep(GAP_SECONDS)
                continue
            for _ in range(step[2]):
                problem = self.sender.send(strokes[step[1]])
                if problem:
                    status = SEND_FAILURE_STATUS.get(problem, "failed")
                    return Outcome(status, text, command, intent, detail=self._explain(status, command))
                pressed.append(step[1])
                self.sleep(GAP_SECONDS)
        self._last[key] = now
        log.info("Macro %s trace (key>screen after each wait; gui 0=cockpit 1=right panel 2=left panel 6=galaxy map): %s",
                 command.id, ", ".join(trace) if trace else "none")
        if self._no_button:
            return Outcome("no_button", text, command, intent, detail=self._explain("no_button", command))
        if self._role_status:
            return Outcome(self._role_status, text, command, intent, detail=self._explain(self._role_status, command))
        if command.id == "request_docking":
            self._check_docking_later()
        if quiet and self.echo is not None:
            self.echo.mute(quiet, 6)            # the game's "map closed" can arrive a moment after the last key
        return Outcome("done", text, command, intent, keys=" > ".join(dict.fromkeys(pressed)),
                       detail=command.do_text(intent) + ".")

    SLOW_PRESSES = 3                  # the first presses are checked one by one (a part near the start is found at once); after that she presses ahead
    SUBSYSTEM_PRESSES = 24            # more than any ship has (weapons first, then the parts): after this many "next subsystem" she gives up

    def _subsystem_step(self, key, strokes, pressed, trace):
        boost = self.journal_boost
        if boost is not None:
            boost(40)                                               # look at the journal ten times a second while this runs
        try:
            return self._subsystem_walk(key, strokes, pressed, trace)
        finally:
            if boost is not None:
                boost(0)

    def _subsystem_walk(self, key, strokes, pressed, trace):
        """Presses Next Subsystem until the game's journal says the wanted part is selected. The journal writes a ShipTargeted
        line for every change, so she checks after each press instead of counting blind. Sets self._role_status when it cannot
        be done. Returns None, or the sender's problem text."""
        from control import subsystems
        state = self.state_provider()
        if state is None or not getattr(state, "target_locked", False):
            self._role_status = "no_target"
            return None
        if int(getattr(state, "target_scan", 0) or 0) < 3:
            self._role_status = "no_scan"
            return None

        def right_one():
            return subsystems.matches(key, state.target_subsystem, state.target_subsystem_readable)
        if right_one():
            trace.append("sub>already")
            return None
        seen = [state.target_subsystem] if state.target_subsystem else []
        action = "CycleNextSubsystem"
        way = subsystems.shorter_way(subsystems.which(state.target_subsystem, state.target_subsystem_readable), key)
        if way == "previous":                                       # fewer presses the other way round (Previous Subsystem is optional)
            try:
                back, _why = self.book.lookup("CyclePreviousSubsystem")
            except Exception:
                back = None
            if back is not None:
                strokes = dict(strokes)
                strokes["CyclePreviousSubsystem"] = back
                action = "CyclePreviousSubsystem"
        log.info("Sub target: going %s from %r to %s", "backwards" if action == "CyclePreviousSubsystem" else "forwards",
                 state.target_subsystem_readable or state.target_subsystem or "nothing", key)
        opposite = "CycleNextSubsystem" if action == "CyclePreviousSubsystem" else "CyclePreviousSubsystem"
        if opposite not in strokes:
            try:
                back, _why = self.book.lookup(opposite)
            except Exception:
                back = None
            if back is not None:
                strokes = dict(strokes)
                strokes[opposite] = back
        can_press_ahead = opposite in strokes and self.settings.get("subtarget.press_ahead", True)
        for number in range(self.SUBSYSTEM_PRESSES):
            if number == self.SLOW_PRESSES and can_press_ahead:
                return self._subsystem_press_ahead(key, state, strokes, action, opposite, seen, number, pressed, trace)
            before = state.target_seq
            problem = self.sender.send(strokes[action], hold=0.1)
            pressed.append(action)
            if problem:
                return problem
            started = time.monotonic()
            for _ in range(40):                                     # up to 2 seconds for the journal to catch up (checks every 0.05 s)
                self.sleep(0.05)
                if state.target_seq != before or not state.target_locked:
                    break
            log.info("Sub target: the journal answered %.2f s after the key", time.monotonic() - started)
            if not state.target_locked:
                self._role_status = "no_target"
                return None
            if state.target_seq == before:
                log.warning("Sub target: pressed Next Subsystem but the journal said nothing (seen so far: %s)", seen)
                trace.append("sub>unread")
                self._role_status = "sub_unread"
                return None
            name = state.target_subsystem_readable or state.target_subsystem
            log.info("Sub target: selected %r (%r)", name, state.target_subsystem)
            if right_one():
                trace.append("sub>%d" % (number + 1))
                return None
            if not state.target_subsystem:                          # it wrapped round to "no subsystem": keep going
                continue
            if seen and state.target_subsystem == seen[-1]:
                continue                                            # the game wrote the same part twice (Benny's 11:17 log): press again
            if state.target_subsystem in seen:
                break                                               # back where it started: this ship does not have it
            seen.append(state.target_subsystem)
        log.info("Sub target: %s not found; this ship showed %s", key, seen)
        trace.append("sub>none")
        self._role_status = "no_subsystem"
        return None

    FAST_HOLD = 0.06                  # press ahead: how long each key is held, then a short pause (about 0.18 s per press instead of 0.6)
    FAST_STEPS = 3
    FAST_STEP_SECONDS = 0.04
    FAST_MAX = 30

    @staticmethod
    def _ring_complete(names):
        """True when a part shows up again after a different one (the list has gone all the way round). The same part twice in a row
        is NOT that: the game writes e.g. 'Drive' twice."""
        seen = set()
        previous = None
        for name in names:
            if name and name != previous and name in seen:
                return True
            if name:
                seen.add(name)
            previous = name
        return False

    def _entries_since(self, state, seq):
        """The ShipTargeted lines since `seq` as (subsystem, readable), oldest first."""
        history = getattr(state, "target_history", None) or []
        found = [(sub, readable) for number, sub, readable in history if number > seq]
        if not found and state.target_seq > seq:                    # no history kept: only the newest line is known
            found = [(state.target_subsystem, state.target_subsystem_readable)]
        return found

    def _wait_for_entries(self, state, seq, count, seconds=1.5):
        """Waits until `count` new lines have arrived since `seq`, or the time is up. Returns how many arrived."""
        for _ in range(int(seconds / 0.05)):
            if len(self._entries_since(state, seq)) >= count or not state.target_locked:
                break
            self.sleep(0.05)
        return len(self._entries_since(state, seq))

    def _subsystem_press_ahead(self, key, state, strokes, action, opposite, seen, used, pressed, trace):
        """The long way round (heavily armed ships have twenty-odd parts, and the game's journal answers about half a second after each
        key): press the key every ~0.18 s WITHOUT waiting for each answer, read the answers as they come, stop at the first one that is
        the wanted part, then step back over the few extra presses. If anything is unclear she carefully steps one at a time instead.
        Returns None (the answer is in self._role_status / trace) or the sender's problem text."""
        from control import subsystems

        def right_one():
            return subsystems.matches(key, state.target_subsystem, state.target_subsystem_readable)

        def tap(name):
            problem = self.sender.send(strokes[name], hold=self.FAST_HOLD)
            pressed.append(name)
            for _ in range(self.FAST_STEPS):
                self.sleep(self.FAST_STEP_SECONDS)
            return problem

        start = state.target_seq
        sent, found_at, names, wrapped = 0, 0, [], False
        while sent < self.FAST_MAX and used + sent < self.SUBSYSTEM_PRESSES + 6:
            problem = tap(action)
            if problem:
                return problem
            sent += 1
            entries = self._entries_since(state, start)
            for index, (sub, readable) in enumerate(entries, 1):
                if subsystems.matches(key, sub, readable):
                    found_at = found_at or index
            if not state.target_locked:
                self._role_status = "no_target"
                return None
            names = [sub for sub, _ in entries]
            if found_at:
                break
            if self._ring_complete(names) or any(not n for n in names[1:]):      # came round again / wrapped to "no subsystem"
                wrapped = True
                break
        arrived = self._wait_for_entries(state, start, sent)
        entries = self._entries_since(state, start)
        log.info("Sub target: pressed ahead %d times, %d answers read, wanted part was answer number %s", sent, arrived, found_at or "none")
        if not state.target_locked:
            self._role_status = "no_target"
            return None
        if right_one():
            trace.append("sub>fast%d" % sent)
            return None
        if found_at:
            over = len(entries) - found_at
            if over > 0:                                           # back over the presses that went past it, also without waiting for each
                mark = state.target_seq
                for _ in range(over):
                    problem = tap(opposite)
                    if problem:
                        return problem
                self._wait_for_entries(state, mark, over)
                log.info("Sub target: stepped back %d over-presses", over)
                if right_one():
                    trace.append("sub>fast%d-%d" % (sent, over))
                    return None
        if wrapped and not found_at:
            log.info("Sub target: %s not found; this ship showed %s", key, sorted(set(n for n in names if n)))
            trace.append("sub>none")
            self._role_status = "no_subsystem"
            return None
        # Unclear (a press was lost, or it was passed): careful single steps. A little back first when it was passed, then forwards.
        order = ([opposite] * 6 + [action] * 6) if found_at else [action] * 8
        for name in order:
            before = state.target_seq
            problem = self.sender.send(strokes[name], hold=0.1)
            pressed.append(name)
            if problem:
                return problem
            for _ in range(40):
                self.sleep(0.05)
                if state.target_seq != before or not state.target_locked:
                    break
            if not state.target_locked:
                self._role_status = "no_target"
                return None
            if right_one():
                trace.append("sub>fast-fixed")
                return None
        log.info("Sub target: %s not found after pressing ahead; this ship showed %s", key, sorted(set(n for n in names if n)))
        trace.append("sub>none")
        self._role_status = "no_subsystem"
        return None

    def _go_to_tab(self, number, strokes, pressed, trace, start=0, panel="left"):
        """The 'tab N' macro step. Looks at the left panel to find the tab it opened on and walks to tab N; if she cannot see the
        screen it presses next tab N times (the old behaviour, which assumes the panel opened on Navigation).
        Returns None, or the sender's problem text if a key could not be pressed."""
        from control import panel_reader
        problems = []

        def press(action):
            problem = self.sender.send(strokes[action], hold=0.15)
            pressed.append(action)
            if problem:
                problems.append(problem)

        if self.settings.get("panel.read_screen", True):
            reader = self.panel_reader or panel_reader.capture_screen
            seen = {"ok": False}
            notes, shots = [], []

            def read():
                picture = reader()
                found = panel_reader.find_tab(picture, near_y=self._tab_height.get(panel))
                seen["ok"] = seen["ok"] or found is not None
                if found is not None:
                    self._tab_height[panel] = found["y"]
                if picture is not None and len(shots) < 8:
                    shots.append((len(notes), picture))
                return found
            try:
                done = panel_reader.goto_tab(read, lambda: press("CycleNextPanel"), lambda: press("CyclePreviousPanel"),
                                             self.sleep, number, note=notes.append, memory=self._tab_memory[panel],
                                             last_index=7 if panel == "right" else None)
            except Exception:
                log.exception("Looking at the panel failed")
                done = False
            if not done:
                log.info("Panel walk to tab %d: %s", number, "; ".join(notes) if notes else "no looks")
                self._save_panel_masks(shots)
            if problems:
                return problems[0]
            if done:
                trace.append("%stab%d>seen" % ("r" if panel == "right" else "", number))
                log.info("Panel: she looked at the screen and went to %s tab %d.", panel, number)
                return None
            self._tab_height.pop(panel, None)                 # forget what she thought she knew: next time look afresh
            self._tab_memory[panel].clear()
            if panel == "right":
                log.info("Panel: she could not read the right panel, so she pressed nothing more.")
                return "no_screen"
            log.info("Panel: she could not read the screen (%s), so she counted the tab presses instead.",
                     "tab bar not found" if not seen["ok"] else "the tab did not move as expected")
        if panel == "right":
            return "no_screen"                                  # the right panel cannot be counted blind (it opens on its last tab)
        action = "CycleNextPanel" if number >= start else "CyclePreviousPanel"
        for _ in range(abs(number - start)):             # blind: she assumes the panel is on tab `start` (Navigation unless told)
            press(action)
            if problems:
                return problems[0]
            self.sleep(0.5)
        return None

    def _role_step(self, step, strokes, pressed, trace):
        """The 'role tab X' and 'role pick N kind' macro steps (the bottom panel). She looks at the panel, see control/role_walk.py.
        Sets self._role_status when the vessel is missing or its button is greyed out. Returns None or the sender's problem text."""
        from control import panel_reader, role_walk
        reader = self.panel_reader or panel_reader.capture_screen
        problems, shots = [], []

        def panel_open():
            """Status.json says the role panel (GuiFocus 4) is still the open panel. Before EVERY key and every look: the log showed a
            key that closed the panel, and the keys after it went into the cockpit."""
            if self._gui_focus() not in (4, "?"):
                raise role_walk.PanelClosed()

        def press(action):
            panel_open()
            if action in ("UI_Up", "UI_Down"):
                from control.binds import MODIFIER_KEYS, _norm_key
                if _norm_key(strokes[action].key) in MODIFIER_KEYS and not strokes[action].modifiers:
                    raise role_walk.UnsafeKey(action)
            problem = self.sender.send(strokes[action], hold=0.15)
            pressed.append(action)
            if problem:
                problems.append(problem)

        def read():
            panel_open()
            picture = reader() if self.settings.get("panel.read_screen", True) else None
            seen = role_walk.read_all(picture)
            if picture is not None and len(shots) < 8:
                shots.append(("role%d" % len(shots), picture))
            return seen

        notes = []
        for action in ("UI_Down", "UI_Up", "UI_Right", "UI_Left", "UI_Select", "CycleNextPanel", "CyclePreviousPanel"):
            if action in strokes and action not in self._role_keys_logged:
                self._role_keys_logged.add(action)
                try:
                    others = ", ".join(self.book.conflicts(action)) or "nothing else"
                except Exception:
                    others = "?"
                log.info("Role panel key: %s = %s%s (also on: %s)", action, "+".join(list(strokes[action].modifiers) + [""]) if strokes[action].modifiers else "",
                         strokes[action].key, others)
        try:
            return self._role_step_inner(step, press, read, notes, problems, shots, trace)
        except role_walk.UnsafeKey as error:
            log.warning("Role panel: %s is only bound to a bare Shift/Control/Alt key on the keyboard, so she did not press it. %s", error, "; ".join(notes))
            trace.append("unsafe_key")
            self._role_status = "cannot_key"
            return None
        except role_walk.PanelClosed:
            log.warning("Role panel: the panel closed by itself, so she pressed nothing more. %s", "; ".join(notes))
            trace.append("panel_closed")
            self._save_panel_masks(shots, "role")
            self._no_button = True
            return None

    def _role_step_inner(self, step, press, read, notes, problems, shots, trace):
        from control import role_walk
        if step[0] == "roletab":
            result = role_walk.go_to_tab(read, press, self.sleep, step[1], note=notes.append)
            log.info("Role panel: walk to tab %d: %s (%s)", step[1], result, "; ".join(notes) or "no notes")
            if problems:
                return problems[0]
            trace.append("roletab%d>%s" % (step[1], result))
            if result != "ok":                       # unreadable or failed: she does not press blind in the cockpit
                self._save_panel_masks(shots, "role")
                self._no_button = True
            return None
        tab = {"nomad": 1, "slf": 1, "rhino": 2, "scarab": 2, "srv": 2, "disembark": 0}[step[2]]
        result, _ = role_walk.pick(read, press, self.sleep, tab, step[1], note=notes.append)
        log.info("Role panel: pick %s (row %s): %s (%s)", step[2], step[1], result, "; ".join(notes) or "no notes")
        if problems:
            return problems[0]
        trace.append("rolepick>%s" % result)
        if result == "ok":
            self.sleep(0.8)
            return None
        self._save_panel_masks(shots, "role")
        if result == "missing":
            self._role_status = {"nomad": "no_nomad", "slf": "no_slf"}.get(step[2], "no_srv")
        elif result == "blocked":
            state = self.state_provider()
            altitude = getattr(state, "altitude", None) if state is not None else None
            flags = getattr(state, "status_flags", 0) or 0
            self._role_status = "cannot_" + role_walk.blocked_reason(step[2], flags, altitude)
        else:
            self._no_button = True
        return None

    @staticmethod
    @staticmethod
    def _save_panel_masks(shots, name=""):
        """When a look fails, keeps a few small black-and-white 'what is bright' maps in data/panel_debug (never the game
        picture) so the diagnostics zip can show what she saw."""
        from control import panel_reader, role_reader
        from core import paths
        try:
            folder = paths.DATA_DIR / "panel_debug"
            folder.mkdir(parents=True, exist_ok=True)
            for old in sorted(folder.glob("*.png"), key=lambda f: f.stat().st_mtime)[:-24]:
                old.unlink()
            stamp = __import__("time").strftime("%H%M%S")
            for index, (when, picture) in enumerate(shots):
                label = when if isinstance(when, str) else str(index)
                label = "".join(c if c.isalnum() else "_" for c in label)[:30]
                target = folder / ("%s-%s-%d-%s.png" % (stamp, name or "walk", index, label))
                if name == "role":
                    role_reader.map_png(picture, target)              # the role panel: bright / grey-button / orange levels
                else:
                    panel_reader.mask_png(picture, target)
        except Exception:
            log.debug("Could not save the panel maps", exc_info=True)

    def _select_button(self, strokes, pressed, trace):
        """The 'select button' macro step: presses Select on the lit button in the right-hand pane (Request Docking), steering by
        what she SEES, because in the commander's logs the first Select sometimes sends the cursor back to the station row in the
        list (the button goes dark): then she presses Right to get back to the button and Select again.
            button lit        -> press Select, then wait up to 3 s for the game's answer (DockingRequested / panel closing)
            station row lit   -> press Right (at most 2 times)
            nothing           -> look once more; if still nothing she stops
        At most 3 Select presses. She never presses blind when she can read the screen. If she cannot read the screen at all she
        presses Select once, as a plain "UI_Select" step would. When it fails she keeps small black-and-white maps (never the
        picture) for the diagnostics zip.
        Returns None (done), "no_button" (she never found anything to press), or the sender's problem text."""
        from control import panel_reader
        reader = self.panel_reader or panel_reader.capture_screen
        use_screen = self.settings.get("panel.read_screen", True)
        shots = []

        def look(label):
            """'button', 'row', 'none', or None when the screen cannot be read."""
            if not use_screen:
                return None
            try:
                picture = reader()
                if picture is None:
                    return None
                button = panel_reader.find_button(picture)
                row = None if button is not None else panel_reader.find_list_row(picture)
                if len(shots) < 8:
                    shots.append((label, picture))
                log.info("Panel: %s: %s%s", label, panel_reader.describe_button(button),
                         ", cursor on the list row" if row is not None else "")
                return "button" if button is not None else ("row" if row is not None else "none")
            except Exception:
                log.exception("Looking for the button failed")
                return None

        def answered():
            return "DockingRequested" in getattr(self, "_docking_seen", [])

        def send(action, hold):
            problem = self.sender.send(strokes[action], hold=hold)
            pressed.append(action)
            return problem

        selects = rights = 0
        for step in range(7):
            state = look("look %d" % (step + 1))
            if state == "none":
                self.sleep(0.8)                              # the highlight can take a moment: one more look
                state = look("look %d (second)" % (step + 1))
            if state is None:                                # cannot read the screen: one plain Select, as before
                if selects == 0:
                    trace.append("button>unreadable")
                    problem = send("UI_Select", 0.15)
                    return problem
                break
            if state == "none":
                break
            if state == "button":
                if selects >= 3:
                    break
                if selects == 0:
                    trace.append("button>seen")
                    self.sleep(0.4)                          # let the pane finish sliding in: an early press can be ignored
                problem = send("UI_Select", 0.15 if selects == 0 else 0.3)
                if problem:
                    return problem
                selects += 1
                if self._after_select(look, answered):
                    return None
                trace.append("select#%d>no answer" % selects)
                log.info("Panel: Select #%d got no answer from the game (no DockingRequested).", selects)
            else:                                            # "row": the cursor is on the station in the list
                if rights >= 2:
                    break
                trace.append("row>right")
                if rights == 0:
                    self._speak("Docking_Retry", {}, fallback="", plain=True)
                log.info("Panel: the cursor is on the list row, so she presses Right to get back to the button.")
                problem = send("UI_Right", 0.15)
                if problem:
                    return problem
                rights += 1
                self.sleep(1.0)
        self._save_panel_masks(shots, "select" if selects else "nobutton")
        if selects == 0:
            trace.append("button>not seen")
            log.warning("Panel: she could not find the Request Docking button, so she did not press Select.")
            return "no_button"
        return None

    def _after_select(self, look, answered):
        """After a Select press: True if the game answered (DockingRequested / the panel closed). She does NOT sit and wait for an
        answer that is not coming: half a second after the press she looks, and if the screen has changed to the list row (the
        press bounced) she returns False at once so the caller presses Right. Only when the button is still lit or the screen
        shows nothing she knows does she give the game up to 3 s to answer (the journal is read once a second)."""
        self.sleep(0.5)
        if answered() or self._gui_focus() == 0:
            return True
        if look("after Select") == "row":
            return False
        for _ in range(5):
            self.sleep(0.5)
            if answered() or self._gui_focus() == 0:
                return True
        return False

    def _open_left_panel(self, strokes, pressed, trace, focus_action="FocusLeftPanel", panel_gui=2):
        """The 'open left panel' macro step: gets the left panel open from whatever the game is showing.
        GuiFocus: 0 cockpit, 1 right panel, 2 left panel, 3 comms, 4 role, 5 station services, 6 galaxy map, 7 system map,
        8 orrery, 9 FSS, 10 SAA, 11 codex. Returns None, or the sender's problem text."""
        def press(action):
            problem = self.sender.send(strokes[action], hold=0.15)
            pressed.append(action)
            return problem

        gui = self._gui_focus()
        trace.append("open>gui%s" % gui)
        if gui == panel_gui:
            return None                                  # already open: pressing the key again would CLOSE it
        if gui in (5, 6, 7, 8, 9, 10, 11):               # a full screen is in the way: Back out of it first
            problem = press("UI_Back")
            if problem:
                return problem
            self.sleep(1.2)
            gui = self._gui_focus()
            trace.append("back>gui%s" % gui)
            if gui in (5, 6, 7, 8, 9, 10, 11):
                log.warning("Panel: the screen (gui %s) would not close, so she did not press more keys.", gui)
                return "failed"
        if gui == panel_gui:
            return None
        for attempt in range(2):
            problem = press(focus_action)
            if problem:
                return problem
            gui = self._gui_focus()
            for _ in range(8):                           # poll instead of a fixed wait: usually open within half a second
                if gui == panel_gui or gui == "?":
                    break
                self.sleep(0.25)
                gui = self._gui_focus()
            if gui == panel_gui or gui == "?":
                self.sleep(0.5 if gui == panel_gui else 1.4)     # let the panel finish sliding in (Status.json unreadable: wait the old time)
            trace.append("focus>gui%s" % gui)
            if gui in (panel_gui, "?"):                   # open, or Status.json cannot tell: carry on as the macro always did
                return None
            if gui != 0:                                 # something else opened: one more press would only close it
                break
        return None

    def _key_clashes(self, strokes):
        """Writes a log line (once per action) when a key a macro presses is also bound to another ship action. Never spoken."""
        notes = []
        for action in strokes:
            try:
                others = self.book.conflicts(action)
            except Exception:
                continue
            if others:
                text = "%s is on the same key as %s" % (action, ", ".join(others[:3]))
                notes.append(text)
                if action not in self._clash_warned:
                    self._clash_warned.add(action)
                    log.warning("Key clash: %s. Elite may do the wrong thing when the macro presses it. "
                                "Give one of them a different key in Elite's controls.", text)
        return notes

    @staticmethod
    def _explain(status, command):
        label = command.label
        return {
            "unbound": "%s has no key in your Elite controls." % (label[0].upper() + label[1:]),
            "joystick_only": "%s is only bound to a joystick button. Bind a keyboard key to it as well." % (label[0].upper() + label[1:]),
            "unknown_key": "I don't know the key bound to %s." % label,
            "no_file": "I can't find your Elite Dangerous controls file.",
            "not_in_file": "Your controls file has no entry for %s." % label,
            "game_not_active": "Elite Dangerous isn't the active window, so I haven't pressed anything.",
            "not_windows": "I can only press keys on Windows.",
            "failed": "I couldn't press the key.",
            "no_button": "I couldn't see the button on the panel, so I didn't press anything.",
            "no_nomad": "There is no Nomad on board.",
            "no_slf": "There is no fighter in the hangar.",
            "no_srv": "There is no SRV in the bay.",
            "cannot_landed": "You have to be landed for that.",
            "cannot_high30": "The Rhino needs you at 30 metres or lower.",
            "cannot_slf_low": "The fighter needs you at 500 metres or higher.",
            "cannot_close": "You're too close to the planet for that.",
            "cannot_key": "UI Down is only on a bare Shift key on the keyboard. Give it another keyboard key in Elite's controls.",
            "cannot_other": "The game says that can't be deployed right now.",
            "no_target": "You have no ship locked.",
            "no_scan": "That ship has not been fully scanned yet, so it has no subsystems to pick.",
            "no_subsystem": "That ship does not show that subsystem.",
            "sub_unread": "I could not tell which subsystem is selected, so I stopped.",
        }.get(status, "That didn't work.")

    # ---- checking without pressing anything (used by the dashboard) ----
    def explain(self, text):
        """What WOULD happen for this sentence. Presses nothing. Returns a list of plain sentences."""
        matches = []
        single = self.matcher.match(text)
        matches = [single] if single is not None else self.matcher.split(text)
        if not matches:
            return ["I don't recognise: %s" % text]
        lines = []
        for match in matches:
            command = match.command
            if command.service:
                lines.append("%s -> ask Void Compass (%s)" % (command.do_text(match.intent), command.service[1]))
                continue
            if command.macro:
                lines.append(self._explain_macro(command, match.intent))
                continue
            action, doing_text = command.action, None
            stroke, why = self.book.lookup(action)
            if stroke is None:
                lines.append("%s -> %s (%s)" % (doing_text or command.do_text(match.intent), self._explain(
                    {binds.UNBOUND: "unbound", binds.JOYSTICK_ONLY: "joystick_only", binds.UNKNOWN_KEY: "unknown_key",
                     binds.NO_FILE: "no_file", binds.NOT_IN_FILE: "not_in_file"}.get(why, "failed"), command), action))
            else:
                state = self.current_state(command)
                note = ""
                if match.intent in ("on", "off") and state is not None and state == (match.intent == "on"):
                    note = " (already %s, so she would just say so)" % command.words[0 if match.intent == "on" else 1]
                lines.append("%s -> press %s (%s)%s" % (doing_text or command.do_text(match.intent), stroke.describe(), action, note))
        return lines

    def _explain_macro(self, command, intent):
        from control.macros import actions_in, parse_macro
        try:
            steps = parse_macro(self.macro_steps(command))
        except ValueError as error:
            return "%s -> the macro in your settings is wrong: %s" % (command.do_text(intent), error)
        missing = [a for a in actions_in(steps) if self.book.lookup(a)[0] is None]
        if missing:
            return "%s -> macro needs keyboard keys for: %s" % (command.do_text(intent), ", ".join(missing))
        return "%s -> macro of %d steps (%s)" % (command.do_text(intent), len(steps), ", ".join(actions_in(steps)))

    def binding_report(self):
        """Every command checked against your keys. Returns (working_count, [(label, reason sentence), ...])."""
        working, problems = 0, []
        seen = set()
        from control.macros import actions_in, parse_macro
        pairs = []
        for c in self.matcher.commands:
            if c.service:
                continue                      # Void Compass commands need no key
            if c.macro:
                try:
                    pairs += [(c, a) for a in actions_in(parse_macro(self.macro_steps(c)))]
                except ValueError:
                    problems.append((c.label, "the macro in your settings is wrong"))
            else:
                pairs.append((c, c.action))
        for command, action in pairs:
            if action in seen:
                continue
            seen.add(action)
            stroke, why = self.book.lookup(action)
            if stroke is not None:
                working += 1
            elif why == binds.NO_FILE:
                return 0, [("everything", self._explain("no_file", command))]
            else:
                status = {binds.UNBOUND: "unbound", binds.JOYSTICK_ONLY: "joystick_only", binds.UNKNOWN_KEY: "unknown_key",
                          binds.NOT_IN_FILE: "not_in_file"}.get(why, "failed")
                problems.append((command.label, self._explain(status, command)))
        return working, problems

    @staticmethod
    def _nice(action):
        """UI_Select -> 'UI Select', CycleNextPanel -> 'Cycle Next Panel' (what the Elite controls screen calls it, roughly)."""
        import re
        return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", action.replace("_", " "))

    def binding_conflicts(self):
        """Keys that one of her commands presses but Elite ALSO gives to another ship action (so a press may do the wrong thing).

        Returns a list of sentences, one per clash, each saying what to change in Elite's controls. Empty when all is clear.
        """
        from control.macros import actions_in, parse_macro
        actions = []
        for c in self.matcher.commands:
            if c.service:
                continue
            if c.macro:
                try:
                    wanted = actions_in(parse_macro(self.macro_steps(c)))
                except ValueError:
                    continue
            else:
                wanted = [c.action]
            for action in wanted:
                if action not in actions:
                    actions.append(action)
        found = []
        for action in actions:
            try:
                others = self.book.conflicts(action)
                stroke, _why = self.book.lookup(action)
            except Exception:
                continue
            if not others or stroke is None:
                continue
            found.append("%s (key %s) is also used by %s. Change one of them in Elite: Options > Controls." % (
                self._nice(action), stroke.describe(), ", ".join(self._nice(o) for o in others[:4])))
        return found

    # ---- telling you ----
    def _finish(self, outcomes, speak, text):
        self.last_outcomes = outcomes
        for outcome in outcomes:
            log.info("Command %r -> %s %s (%s)", outcome.text, outcome.status,
                     outcome.command.id if outcome.command else "", outcome.keys)
            if self.bus is not None:
                self.bus.publish("voice.command", {
                    "status": outcome.status, "command": outcome.command.id if outcome.command else "",
                    "intent": outcome.intent, "keys": outcome.keys, "text": outcome.text,
                    "summary": outcome.detail})
        if speak:
            self._say(outcomes)

    def _say(self, outcomes):
        if self.speech is None or not self.settings.get("speech.enabled", True):
            return
        outcomes = [o for o in outcomes if o.status != "duplicate"]
        if not outcomes:
            return
        good = [o for o in outcomes if o.status == "done"]
        bad = [o for o in outcomes if o.status != "done"]
        if bad:
            outcome = bad[0]
        elif not self.settings.get("commands.confirm", True) or getattr(self, "auto_run", False):
            return
        elif len(good) > 1:
            self._speak("CommandMulti", {"count": len(good)}, fallback="Done.")
            return
        else:
            outcome = good[0]
            if (outcome.command is not None and outcome.command.id in ("auto_launch", "request_docking")
                    and outcome.status == "done" and getattr(self, "macro_spoke", False)):
                return                          # the macro already talked her way through it
        label = outcome.command.label if outcome.command else ""
        fields = {
            "doing": outcome.detail.rstrip("."),
            "label": label, "Label": label[:1].upper() + label[1:],
            "state": (outcome.command.words[0 if outcome.intent == "on" else 1] if outcome.command else ""),
            "keys": outcome.keys,
        }
        self._speak(LINE_FOR_STATUS.get(outcome.status, "CommandFailed"), fields, fallback=outcome.detail)

    def _speak(self, key, fields, fallback, plain=False):
        if self.dialogue is not None:
            info = self.settings.get("personality.style", "personality") == "info"
            mood = "" if info else effective_mood(self.settings)
            line = self.dialogue.pick(key, mood, bool(self.settings.get("speech.allow_mature", False)), False)
        else:
            line = None
        text = fallback
        if line is not None:
            try:
                text = line.text.format(**fields)
            except (KeyError, IndexError, ValueError):
                text = fallback
            text = personalise(text, self.settings)
            if self.flavour is not None and not line.audio and not plain:
                text = self.flavour.apply(text, "normal")
        if not text:
            return
        self.speech.say(text=text, priority="normal", event_name="voice.command")
