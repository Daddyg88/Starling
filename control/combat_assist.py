"""
Combat helpers: pips on fire and heat sinks.

All three only press the keys YOU bound in Elite (same rules as voice commands: Elite must be the window in front,
and the action needs a KEYBOARD key as well as any joystick button).

Auto pips
    While your hardpoints are out (or you are in analysis mode, for mining lasers) and you HOLD a fire button, she moves the power pips to weapons.
    When you let go (and stay off the button for a moment) she resets and sends pips to systems and engines.
    She finds your fire buttons from Elite's controls file (Primary fire and Secondary fire): keyboard keys, and
    joystick buttons on the X52. You can also list extra buttons in settings.json under combat_assist.fire_buttons.

Heat sinks
    Elite does not tell programs the heat percentage either. The game's own overheat warning (about 100%) is the
    earliest signal there is, so she fires a heat sink then. Never while docked, landed or fuel scooping.
"""

import re
import threading
import time

from control import inputs
from core.logger import get_logger

log = get_logger("combat_assist")

DOCKED_BIT, LANDED_BIT, SUPERCRUISE_BIT, HARDPOINTS_BIT, SCOOP_BIT, ANALYSIS_BIT = 0, 1, 4, 6, 11, 27
FIRE_ACTIONS = ("PrimaryFire", "SecondaryFire")
POLL_SECONDS = 0.03
IDLE_POLL_SECONDS = 0.4
DEFAULT_PIPS_UP = ["IncreaseWeaponsPower"] * 4
DEFAULT_PIPS_DOWN = ["ResetPowerDistribution", "IncreaseSystemsPower", "IncreaseEnginesPower"]


def _flag(state, bit):
    flags = getattr(state, "status_flags", None)
    return bool(flags is not None and (flags >> bit) & 1)


def hardpoints_out(state):
    return _flag(state, HARDPOINTS_BIT)


def key_spec_from_elite(name):
    """'Key_Space' -> 'key:Space', 'Key_Numpad_1' -> 'key:Numpad1'. None if the button reader cannot watch that key."""
    name = re.sub(r"^key_", "", (name or ""), flags=re.I).replace("_", "")
    for known in inputs.VK:
        if known.lower() == name.lower():
            return inputs.key_spec(known)
    return None


def fire_specs(book, reader):
    """Every button that fires your weapons, as button specs the ButtonReader understands."""
    found = []
    for action in FIRE_ACTIONS:
        for slot in book.slots(action):
            if slot.is_empty() or slot.modifiers:
                continue                                    # a shifted button is not a plain trigger
            device, key = slot.device, slot.key
            if device.lower() == "keyboard":
                spec = key_spec_from_elite(key)
                if spec:
                    found.append(spec)
                continue
            match = re.fullmatch(r"Joy_(\d+)", key or "")
            if not match or not 1 <= int(match.group(1)) <= 32:
                continue
            button = int(match.group(1))
            flat = re.sub(r"[^0-9a-z]", "", device.lower())
            if re.fullmatch(r"[0-9a-f]{8}", flat):
                found.append("joy:%s:%s:%d" % (flat[:4].upper(), flat[4:].upper(), button))
            elif "x52" in flat:
                for stick in reader.x52_devices():
                    found.append(inputs.joy_spec(stick, button))
    return list(dict.fromkeys(found))


class CombatAssist:
    def __init__(self, bus, settings, book, sender, reader, state_provider, speech=None, dialogue=None,
                 clock=time.monotonic, sleep=time.sleep):
        self.bus, self.settings, self.book, self.sender, self.reader = bus, settings, book, sender, reader
        self.state_provider, self.speech, self.dialogue = state_provider, speech, dialogue
        self.clock, self.sleep = clock, sleep
        self._running = False
        self._thread = None
        self._boosted = False
        self._released_at = None
        self._last_sink = -999.0
        self._warned = set()
        self._specs = []
        self._specs_at = -999.0
        self.last_result = ""

    # ---- settings ----
    def option(self, name, default=None):
        return self.settings.get("combat_assist." + name, default)

    # ---- wiring ----
    def attach(self):
        for name in ("Overheating", "HeatWarning", "HeatDamage"):
            self.bus.subscribe(name, self.on_heat)
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="combat-assist", daemon=True)
        self._thread.start()

    def detach(self):
        self._running = False
        for name, handler in (("Overheating", self.on_heat), ("HeatWarning", self.on_heat), ("HeatDamage", self.on_heat)):
            self.bus.unsubscribe(name, handler)
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    # ---- pressing keys ----
    def press(self, action, hold=None):
        stroke, why = self.book.lookup(action)
        if stroke is None:
            self.last_result = "unbound"
            log.warning("Combat assist: no keyboard key for %s (%s)", action, why)
            self._tell_once(action)
            return False
        problem = self.sender.send(stroke) if hold is None else self.sender.send(stroke, hold=hold)
        self.last_result = problem or "done"
        if problem:
            log.info("Combat assist: %s was not pressed (%s)", action, problem)
        return not problem

    def _tell_once(self, action):
        if action in self._warned or self.speech is None:
            return
        self._warned.add(action)
        self.speech.say(text="Combat assist can't press %s, Commander. It has no keyboard key in Elite's controls. "
                             "Add one and it will work." % action, priority="normal", event_name="combat_assist.problem")

    def _say(self, key):
        if self.speech is None or self.dialogue is None:
            return
        from personality.mood_engine import effective_mood
        line = self.dialogue.pick(key, effective_mood(self.settings), bool(self.settings.get("speech.allow_mature", False)), False)
        if line is not None:
            self.speech.say(text=line.text.replace("||", " "), priority="low", event_name=key)

    # ---- is it a fight? ----
    def fighting(self):
        """Weapons are in use: hardpoints out, or (mining, scanning, limpets) the cockpit is in analysis mode."""
        state = self.state_provider()
        armed = hardpoints_out(state) or (bool(self.option("pips_analysis", True)) and _flag(state, ANALYSIS_BIT))
        return armed and not _flag(state, DOCKED_BIT) and not _flag(state, LANDED_BIT) and not _flag(state, SUPERCRUISE_BIT)

    # ---- heat sinks ----
    def on_heat(self, _event):
        if not self.option("heat_sink", True):
            return
        state = self.state_provider()
        if _flag(state, DOCKED_BIT) or _flag(state, LANDED_BIT) or _flag(state, SCOOP_BIT):
            return
        now = self.clock()
        if now - self._last_sink < float(self.option("sink_gap_seconds", 8.0)):
            return
        self._last_sink = now
        log.info("Deploying a heat sink")
        threading.Thread(target=self._sink_worker, name="heat-sink", daemon=True).start()

    def _sink_worker(self):
        try:
            if self.press("DeployHeatSink"):
                self._say("CombatAssist_HeatSink")
        except Exception:
            log.exception("Heat sink failed")

    # ---- pips ----
    def fire_buttons(self):
        now = self.clock()
        if now - self._specs_at > 5.0:
            extra = self.option("fire_buttons", "") or ""
            if isinstance(extra, str):
                extra = [x.strip() for x in extra.split(",") if x.strip()]
            try:
                found = fire_specs(self.book, self.reader)
            except Exception:
                log.exception("Could not work out your fire buttons")
                found = []
            self._specs = list(dict.fromkeys(found + list(extra)))
            self._specs_at = now
        return self._specs

    def firing(self):
        return any(self.reader.is_down(spec) for spec in self.fire_buttons())

    def poll_once(self):
        """One look at the fire buttons. Returns what it did: "up", "down" or "" (for tests)."""
        if not self.option("pips", True) or not self.fighting():
            if self._boosted and not self.fighting():
                self._boosted, self._released_at = False, None          # the fight ended some other way
            return ""
        down = self.firing()
        now = self.clock()
        if down:
            self._released_at = None
            if not self._boosted:
                self._boosted = True
                self._run_steps(self.option("pips_firing", DEFAULT_PIPS_UP))
                return "up"
            return ""
        if self._boosted:
            if self._released_at is None:
                self._released_at = now
            elif now - self._released_at >= float(self.option("pips_delay", 1.2)):
                self._boosted, self._released_at = False, None
                self._run_steps(self.option("pips_resting", DEFAULT_PIPS_DOWN))
                return "down"
        return ""

    def _run_steps(self, steps):
        for action in steps or []:
            if not self.press(action):
                if self.last_result != "unbound":
                    return                                              # Elite is not in front: stop quietly
            self.sleep(0.05)

    def _loop(self):
        while self._running:
            try:
                self.poll_once()
            except Exception:
                log.exception("Combat assist poll failed")
            self.sleep(POLL_SECONDS if self.fighting() else IDLE_POLL_SECONDS)
