"""
Auto honk.

When you arrive in a new system she holds down your fire button for a few seconds. If your Discovery
Scanner is on that fire button, that is the "honk" that reveals every body in the system.

Which fire button the scanner is on differs from player to player, so the dashboard has a dropdown:
Off, Primary fire, or Secondary fire. She then looks up the key in your Elite controls file
(the same way voice commands do) and holds it down.

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
DEFAULT_HOLD_SECONDS = 6.0
DEFAULT_DELAY_SECONDS = 2.0
MIN_GAP_SECONDS = 20.0                # never honk twice in a row faster than this


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

    def attach(self):
        self.bus.subscribe("FSDJump", self.on_jump)

    def detach(self):
        self.bus.unsubscribe("FSDJump", self.on_jump)

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

    def _honk(self, mode):
        try:
            self.sleep(float(self.settings.get("autohonk.delay_seconds", DEFAULT_DELAY_SECONDS)))
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
            hold = float(self.settings.get("autohonk.hold_seconds", DEFAULT_HOLD_SECONDS))
            problem = self.sender.send(stroke, hold=hold)
            self.last_result = problem or "done"
            if problem:
                log.warning("Auto honk did not press the key: %s (if this says game_not_active, another window was in front of Elite)", problem)
        except Exception:
            self.last_result = "error"
            log.exception("Auto honk failed")
        finally:
            self._busy = False

    def _tell_once(self, mode):
        if self._warned or self.speech is None:
            return
        self._warned = True
        name = "primary" if mode == "primary" else "secondary"
        self.speech.say(
            text="Auto honk can't work, Commander. Your %s fire button has no keyboard key in Elite. "
                 "Add one in the controls, then it will work." % name,
            priority="normal", event_name="autohonk.problem")
