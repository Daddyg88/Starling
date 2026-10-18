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

from control import binds, sender as sender_module
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


class CommandRunner:
    def __init__(self, bus, speech, dialogue, settings, book=None, sender=None, state_provider=None,
                 matcher=None, flavour=None, clock=time.monotonic, sleep=time.sleep, echo=None, voidcompass=None, route=None, macro_hooks=None, memory=None):
        self.bus = bus
        self.speech = speech
        self.dialogue = dialogue
        self.settings = settings
        self.book = book if book is not None else binds.BindingBook()
        self.sender = sender if sender is not None else sender_module.KeySender()
        self.state_provider = state_provider or (lambda: None)
        self.matcher = matcher or Matcher()
        self.flavour = flavour
        self.echo = echo                 # control/echo.py: tells the event speaker not to repeat what she just did
        self.macro_hooks = macro_hooks or {}     # command id -> function run before its macro; returns (ok, sentence)
        self.memory = memory             # memory/recall.py: "what do you remember"
        self.route = route               # navigation/voice.py: 'plot a neutron route to Colonia'
        self.voidcompass = voidcompass   # control/voidcompass.py (made on first use if not given)
        self.clock = clock
        self.sleep = sleep
        self._last = {}
        self._clash_warned = set()
        self.last_outcomes: List[Outcome] = []

    # ---- wiring ----
    def attach(self):
        self.bus.subscribe("voice.heard", self.on_heard)

    def detach(self):
        self.bus.unsubscribe("voice.heard", self.on_heard)

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
        if not self.addressed(data):
            return
        text = data.get("command") if data.get("wake") else data.get("text")
        if not normalise(text or ""):
            return                      # she only heard her name: VoiceReplies says "Yes?"
        from personality.manners import only_thanks
        if only_thanks(text):
            return                      # a plain "thank you" is not a command; Manners answers it
        deliberate = bool(data.get("wake") or data.get("ptt"))
        self.run_text(text, speak_unknown=deliberate)

    # ---- doing ----
    def run_text(self, text, speak_unknown=True, speak=True):
        """Understand and carry out a sentence. Returns the list of Outcomes."""
        for helper in (self.memory, self.route):       # spoken questions and the route plotter answer for themselves
            if helper is None:
                continue
            try:
                handled = helper.try_handle(text)
            except Exception:
                log.exception("A voice helper failed")
                handled = None
            if handled is not None:
                outcome = Outcome("route", text, None, "press", detail=handled)
                self._finish([outcome], False, text)
                return [outcome]
        matches = []
        single = self.matcher.match(text)
        if single is not None:
            matches = [single]
        else:
            matches = self.matcher.split(text)
        if not matches:
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

    def _run_macro(self, command, intent, text, now, key):
        from control.macros import GAP_SECONDS, actions_in, parse_macro
        try:
            steps = parse_macro(self.macro_steps(command))
        except ValueError as error:
            return Outcome("failed", text, command, intent, detail="The %s macro in your settings is wrong: %s" % (command.label, error))
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
        clash = self._key_clashes(strokes)
        self.sender.require_game = bool(self.settings.get("commands.require_game_focus", True))
        pressed = []
        for step in steps:
            if step[0] == "wait":
                self.sleep(step[1])
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
        return Outcome("done", text, command, intent, keys=" > ".join(dict.fromkeys(pressed)),
                       detail=command.do_text(intent) + "." + clash)

    def _key_clashes(self, strokes):
        """Warns (once per action) when a key a macro presses is also bound to another ship action."""
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
        return (" Warning: " + "; ".join(notes) + ".") if notes else ""

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
        elif not self.settings.get("commands.confirm", True):
            return
        elif len(good) > 1:
            self._speak("CommandMulti", {"count": len(good)}, fallback="Done.")
            return
        else:
            outcome = good[0]
        label = outcome.command.label if outcome.command else ""
        fields = {
            "doing": outcome.detail.rstrip("."),
            "label": label, "Label": label[:1].upper() + label[1:],
            "state": (outcome.command.words[0 if outcome.intent == "on" else 1] if outcome.command else ""),
            "keys": outcome.keys,
        }
        self._speak(LINE_FOR_STATUS.get(outcome.status, "CommandFailed"), fields, fallback=outcome.detail)

    def _speak(self, key, fields, fallback):
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
            if self.flavour is not None and not line.audio:
                text = self.flavour.apply(text, "normal")
        self.speech.say(text=text, priority="normal", event_name="voice.command")
