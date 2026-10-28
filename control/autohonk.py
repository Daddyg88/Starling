"""
Auto honk.

When you arrive in a new system she holds down your fire button for a few seconds. If your Discovery
Scanner is on that fire button, that is the "honk" that reveals every body in the system.

Which fire button the scanner is on differs from player to player, so the dashboard has a dropdown:
Off, Primary fire, or Secondary fire. She then looks up the key in your Elite controls file
(the same way voice commands do) and holds it down.

If the cockpit is in combat mode (not analysis mode) and your hardpoints are away, the fire button would do nothing, so she first presses
your "Cockpit mode" key (if it has a keyboard key), honks, then switches back. Set autohonk.switch_mode to false in settings.json to stop that.

Safety rules:
  * Nothing happens when the setting is Off.
  * Nothing happens while your hardpoints are deployed (the fire button would shoot your weapons).
  * Nothing happens unless Elite is the window in front (same rule as voice commands).
  * Only a button that is also bound to a KEYBOARD key can be pressed. A joystick-only button cannot.
    If that is your case she tells you once, and you can add a keyboard key for it in Elite's controls.
"""

import threading
import time

from core.logger import get_logger

log = get_logger(__name__)

MODES = {"primary": "PrimaryFire", "secondary": "SecondaryFire"}
HARDPOINTS_BIT = 6                    # Status.json flag: hardpoints deployed
ANALYSIS_BIT = 27                     # Status.json flag: the cockpit is in analysis mode
HUD_MODE_ACTION = "PlayerHUDModeToggle"
MODE_SETTLE_SECONDS = 1.2
EXPLAIN = {
    "": "She has not tried to honk yet.",
    "off": "Auto honk is switched off (choose Primary or Secondary fire).",
    "too soon": "She honked less than 20 seconds ago, so she waited.",
    "hardpoints": "Your hardpoints were out, so she did not fire.",
    "unbound": "Your fire button has no KEYBOARD key in Elite's controls. Add one (a second binding is fine) and it will work.",
    "game_not_active": "Elite was not the window in front, so she did not press anything.",
    "not_windows": "Key presses only work on Windows.",
    "unknown_key": "Your fire button is on a key she does not know.",
    "error": "Something went wrong. See logs/starling.log.",
    "done": "She held the fire button. If nothing was scanned, check that the Discovery Scanner is in the fire group you have selected.",
}


def explain(result):
    return EXPLAIN.get(result, "The key press failed: %s" % result)
DEFAULT_HOLD_SECONDS = 6.0
DEFAULT_DELAY_SECONDS = 2.0
MIN_GAP_SECONDS = 20.0                # never honk twice in a row faster than this


def in_analysis_mode(state):
    flags = getattr(state, "status_flags", None)
    return bool(flags is not None and (flags >> ANALYSIS_BIT) & 1)


def hardpoints_out(state):
    flags = getattr(state, "status_flags", None)
    return bool(flags is not None and (flags >> HARDPOINTS_BIT) & 1)


class AutoHonk:
    def __init__(self, bus, settings, book, sender, state_provider, speech=None, sleep=time.sleep,
                 clock=time.monotonic, spawn=None):
        self.bus = bus
        self.settings = settings
        self.book = book
        self.sender = sender
        self.state_provider = state_provider
        self.speech = speech
        self.sleep = sleep
        self.clock = clock
        self.spawn = spawn or self._spawn_thread
        self._busy = False
        self._last = None
        self._warned = False
        self.last_result = ""          # for tests and the log: what happened last time
        self._testing = False

    def attach(self):
        self.bus.subscribe("FSDJump", self.on_jump)
        self.bus.subscribe("journal.arrived", self.on_jump)      # sent for every real jump, even when her jump speech is switched off

    def detach(self):
        self.bus.unsubscribe("FSDJump", self.on_jump)
        self.bus.unsubscribe("journal.arrived", self.on_jump)

    def test_now(self, delay=4.0):
        """The dashboard's test button: honk once after `delay` seconds (click back into Elite). Returns a sentence."""
        mode = str(self.settings.get("autohonk.mode", "off") or "off").lower()
        if mode not in MODES:
            self.last_result = "off"
            return explain("off")
        if self._busy:
            return "She is already honking."
        self._busy = True
        self._testing = True
        self._last = None
        self.last_result = ""
        self.spawn(lambda: self._honk(mode, delay=delay))
        return "Click into Elite now. She will honk in %d seconds, then tell you what happened." % int(delay)

    @staticmethod
    def _spawn_thread(function):
        threading.Thread(target=function, name="auto-honk", daemon=True).start()

    # ---- the event ----
    def on_jump(self, _event):
        mode = str(self.settings.get("autohonk.mode", "off") or "off").lower()
        if mode not in MODES:
            self.last_result = "off"
            return
        now = self.clock()
        if self._busy or (self._last is not None and now - self._last < MIN_GAP_SECONDS):
            self.last_result = "too soon"
            return
        self._busy = True
        self.spawn(lambda: self._honk(mode))

    def _honk(self, mode, delay=None):
        switched = False
        try:
            self.sleep(float(self.settings.get("autohonk.delay_seconds", DEFAULT_DELAY_SECONDS)) if delay is None else float(delay))
            self._last = self.clock()
            if hardpoints_out(self.state_provider()):
                self.last_result = "hardpoints"
                log.info("Auto honk skipped: hardpoints are deployed")
                return
            action = MODES[mode]
            stroke, why = self.book.lookup(action)
            if stroke is None:
                self.last_result = "unbound"
                log.warning("Auto honk: no keyboard key for %s (%s)", action, why)
                self._tell_once(mode)
                return
            state = self.state_provider()
            if (self.settings.get("autohonk.switch_mode", True) and getattr(state, "status_seen", False)
                    and not in_analysis_mode(state)):
                switched = self._toggle_mode()
            hold = float(self.settings.get("autohonk.hold_seconds", DEFAULT_HOLD_SECONDS))
            problem = self.sender.send(stroke, hold=hold)
            self.last_result = problem or "done"
            (log.info if self.last_result != "done" or not getattr(self, "_logged_done", False) else log.debug)("Auto honk: %s", explain(self.last_result))
            self._logged_done = self.last_result == "done"          # the long 'if nothing was scanned...' text only the first time
            if problem:
                log.warning("Auto honk did not press the key: %s (if this says game_not_active, another window was in front of Elite)", problem)
        except Exception:
            self.last_result = "error"
            log.exception("Auto honk failed")
        finally:
            if switched:
                self._toggle_mode()                  # back to the mode you were in
            self._busy = False
            self._announce_result()

    def _toggle_mode(self):
        """Press your Cockpit mode key once. Returns True if it was pressed."""
        stroke, why = self.book.lookup(HUD_MODE_ACTION)
        if stroke is None:
            log.info("Auto honk: the cockpit is in combat mode and there is no keyboard key for %s (%s), so the honk may do nothing", HUD_MODE_ACTION, why)
            return False
        if self.sender.send(stroke):
            return False
        self.sleep(MODE_SETTLE_SECONDS)
        return True

    def _announce_result(self):
        """After the dashboard test button she says what happened (so you do not need the log)."""
        if self._testing and self.speech is not None:
            self.speech.say(text=explain(self.last_result), priority="normal", event_name="autohonk.test")
        self._testing = False

    def _tell_once(self, mode):
        if self._warned or self.speech is None or self._testing:        # the test button speaks its own result
            return
        self._warned = True
        name = "primary" if mode == "primary" else "secondary"
        self.speech.say(
            text="Auto honk can't work, Commander. Your %s fire button has no keyboard key in Elite. "
                 "Add one in the controls, then it will work." % name,
            priority="normal", event_name="autohonk.problem")
