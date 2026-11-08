"""RED ALERT: one switch that changes how she behaves and how the screen looks.

While it is on:
  * she speaks faster (settings red_alert.speed, default 1.2 = 20% quicker)
  * she stops chatting: no idle chit-chat, no pet names or remarks added to her lines. Safety warnings and the answers to your commands
    are never touched
  * a pulsing red glow around the edge of the screen and a very light red tint (ui/red_alert_overlay.py)
It is NEVER saved: closing her or restarting ends it. It also ends by itself after red_alert.minutes (default 30, 0 = never).
Say "red alert" to start it and "stand down" (or "all clear") to end it.
"""

import re
import time

ON = re.compile(r"\b(?:red alert|battle stations|action stations)\b")
OFF = re.compile(r"\b(?:stand down|all clear|stand easy|cancel red alert|end red alert|red alert (?:off|over|cancelled|canceled|ended|finished|clear))\b")
MAX_SPEED = 2.0


def clean(text):
    text = re.sub(r"[^a-z ]", " ", str(text or "").lower())
    return re.sub(r"\s+", " ", text).strip()


def speed_setting(settings):
    try:
        return max(1.0, min(MAX_SPEED, float(settings.get("red_alert.speed", 1.2))))
    except (TypeError, ValueError):
        return 1.2


class RedAlert:
    def __init__(self, settings, speech_provider, kokoro_provider, flavour_provider, narrator=None, clock=time.monotonic, combat_mode=None):
        self.settings = settings
        self.speech_provider = speech_provider
        self.kokoro_provider = kokoro_provider
        self.flavour_provider = flavour_provider
        self.narrator = narrator                  # navigation.voice.Narrator: says a line from the voicepack
        self.clock = clock
        self.combat_mode = combat_mode            # () -> switches the HUD to combat mode (a no-op when it already is)
        self.active = False
        self.since = 0.0

    # ---- the switch ----
    def turn_on(self, announce=True):
        if self.active:
            return False
        self.active, self.since = True, self.clock()
        self._apply(True)
        if announce and self.narrator is not None:
            self.narrator.say("RedAlert_On")
        if self.combat_mode is not None and self.settings.get("red_alert.combat_mode", True):
            try:
                self.combat_mode()
            except Exception:
                pass
        return True

    def turn_off(self, announce=True):
        if not self.active:
            return False
        self.active = False
        self._apply(False)
        if announce and self.narrator is not None:
            self.narrator.say("RedAlert_Off")
        return True

    def toggle(self):
        return self.turn_off() if self.active else self.turn_on()

    def _apply(self, on):
        """Hands the three changes to the parts that own them. Each part is optional (a part that is not running is skipped)."""
        for provider, name, value in ((self.speech_provider, "alert", on), (self.flavour_provider, "red_alert", on)):
            try:
                target = provider()
                if target is not None:
                    setattr(target, name, value)
            except Exception:
                pass
        try:
            kokoro = self.kokoro_provider()
            if kokoro is not None:
                kokoro.speed_boost = speed_setting(self.settings) if on else 1.0
        except Exception:
            pass

    # ---- housekeeping, called about once a second ----
    def tick(self):
        if not self.active:
            return
        try:
            minutes = float(self.settings.get("red_alert.minutes", 30) or 0)
        except (TypeError, ValueError):
            minutes = 30.0
        if minutes > 0 and self.clock() - self.since >= minutes * 60.0:
            self.turn_off()
        else:
            self._apply(True)                                  # the settings may have changed (the speed box): follow them

    # ---- her voice ----
    def try_handle(self, text):
        """The voice helper: returns None when the sentence is not about red alert."""
        said = clean(text)
        if not said:
            return None
        if OFF.search(said):
            return "Standing down." if self.turn_off() else "There is no red alert on."
        if ON.search(said):
            return "Red alert." if self.turn_on() else "Red alert is already on."
        return None
