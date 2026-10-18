"""
THE WATCHER BRIDGE: Starling and the Watcher from Void Compass.

The Watcher is the glowing orb in Void Compass. When its voice is on, it talks. This does two things:

  1. REPLY.  After he speaks, Starling answers in her current mood: kind and supportive when she is happy,
             "shut up, Watcher" when she is not. (voicepacks/default/watcher.json)
  2. WAIT.   If he starts talking at a bad moment (she is speaking or asking you a question, a safety warning
             just happened, weapons are out, you are being interdicted, jumping, overheating, low on fuel...),
             she stops him at once and lets him say it again when it is calm. Lines that are still waiting
             after a few minutes are dropped, because they would be out of date.

How it hears him: it asks Void Compass's Local API for new "voice" events (long polling, almost no traffic).
Everything that talks to the network runs on its own thread; the decisions are in plain methods so the tests
can run them without any thread or network.

Honest limit: Void Compass only tells us AFTER he has started speaking, so at a bad moment you may hear the
first moment of his voice before she cuts him off.
"""

import random
import threading
import time

from control.voidcompass import VoidError
from core.identity import personalise
from core.logger import get_logger
from personality.mood_engine import effective_mood

log = get_logger("watcher")

# Status.json flags that mean "not now"
HARDPOINTS, FSD_CHARGING, LOW_FUEL, OVERHEATING, IN_DANGER, INTERDICTED, FSD_JUMP = 6, 17, 19, 20, 22, 23, 30
BUSY_BITS = (HARDPOINTS, FSD_CHARGING, LOW_FUEL, OVERHEATING, IN_DANGER, INTERDICTED, FSD_JUMP)

CALM_AFTER_CRITICAL_SECONDS = 30.0
HOLD_MAX_SECONDS = 180.0            # a line still waiting after this is stale: drop it
REPLY_START_DELAY_SECONDS = 1.5     # give his voice a moment to actually start before checking if it has ended
REPLY_WAIT_SECONDS = 25.0           # how long we wait for him to finish before giving up on the reply
REPLY_CHANCE = {"always": 1.0, "often": 0.7, "sometimes": 0.4, "never": 0.0}
OFFLINE_RETRY_SECONDS = 10.0


class WatcherBridge:
    def __init__(self, bus, speech, dialogue, settings, client, state_provider=None, ask_provider=None,
                 clock=time.monotonic, rng=None, sleep=time.sleep):
        self.bus = bus
        self.speech = speech
        self.dialogue = dialogue
        self.settings = settings
        self.client = client
        self.state_provider = state_provider or (lambda: None)
        self.ask_provider = ask_provider or (lambda: None)     # the AskManager, to see if a question is open
        self.clock = clock
        self.rng = rng or random.Random()
        self.sleep = sleep
        self._lock = threading.RLock()
        self._last_critical = None
        self.held = None                  # (text, since) he wanted to say at a bad time
        self.reply_due = None             # (deadline, was_waiting_for_voice_to_end)
        self.seq = None
        self._stop = threading.Event()
        self._thread = None

    # ---- wiring ----
    def attach(self):
        self.bus.subscribe("*", self._on_bus)

    def detach(self):
        self.bus.unsubscribe("*", self._on_bus)
        self.stop()

    def _on_bus(self, event):
        if event.priority == "critical":
            self._last_critical = self.clock()

    def start(self):
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="watcher-bridge", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread = None

    # ---- settings ----
    def enabled(self):
        return bool(self.settings.get("voidcompass.enabled", True) and self.settings.get("watcher.enabled", True)
                    and self.settings.get("speech.enabled", True))

    def _mood(self):
        return effective_mood(self.settings)

    # ---- is it a good moment? ----
    def calm(self):
        """True when it is a fine time for someone to start talking."""
        now = self.clock()
        if self._last_critical is not None and now - self._last_critical < CALM_AFTER_CRITICAL_SECONDS:
            return False
        if self.speech is not None and self.speech.is_busy():
            return False
        ask = self.ask_provider()
        if ask is not None and getattr(ask, "pending", None) is not None:
            return False
        state = self.state_provider()
        flags = getattr(state, "status_flags", 0) if state is not None else 0
        return not any((flags >> bit) & 1 for bit in BUSY_BITS)

    # ---- what happens ----
    def handle(self, item):
        """One event from Void Compass: {"type": "voice", "data": {"text", "from"}}."""
        if not self.enabled() or item.get("type") != "voice":
            return
        data = item.get("data") or {}
        if data.get("from") != "watcher":
            return                                    # our own replay, or something sent by another script
        text = str(data.get("text") or "").strip()
        if not text:
            return
        if self.settings.get("watcher.wait_for_calm", True) and not self.calm():
            self._hold(text)
        else:
            self._expect_reply()

    def _hold(self, text):
        with self._lock:
            self.held = (text, self.clock())
            self.reply_due = None
        try:
            self.client.voice_stop()
        except VoidError as error:
            log.info("Could not stop the Watcher: %s", error.message or error.kind)
        log.info("The Watcher spoke at a bad moment; holding his line")

    def _expect_reply(self):
        with self._lock:
            now = self.clock()
            self.reply_due = (now + REPLY_START_DELAY_SECONDS, now + REPLY_WAIT_SECONDS)   # (not before, give up at)

    def tick(self):
        """Run every second or two: let a held line go, and answer him once he has finished."""
        if not self.enabled():
            with self._lock:
                self.held = self.reply_due = None
            return
        with self._lock:
            held, due = self.held, self.reply_due
        now = self.clock()
        if held is not None:
            if now - held[1] > HOLD_MAX_SECONDS:
                with self._lock:
                    self.held = None
                log.info("Dropped a stale Watcher line")
            elif self.calm():
                with self._lock:
                    self.held = None
                try:
                    self.client.voice_say(held[0])
                except VoidError as error:
                    log.info("Could not replay the Watcher's line: %s", error.message or error.kind)
                    return
                self._expect_reply()
            return
        if due is not None:
            if now > due[1]:
                with self._lock:
                    self.reply_due = None
                return
            if now < due[0]:
                return
            try:
                if self.client.voice().get("speaking"):
                    return                                  # still talking: let him finish
            except VoidError:
                return
            with self._lock:
                self.reply_due = None
            if self.calm_for_reply():
                self.reply()

    def calm_for_reply(self):
        """Replies are never worth talking over a warning, so they are skipped rather than delayed."""
        return self.calm()

    def reply(self):
        chance = REPLY_CHANCE.get(str(self.settings.get("watcher.reply", "often")), 0.7)
        if self.rng.random() >= chance or self.speech is None or self.dialogue is None:
            return False
        if self.settings.get("personality.style", "personality") != "personality":
            return False
        mood = self._mood() or "Neutral"
        allow = bool(self.settings.get("speech.allow_mature", False))
        line = self.dialogue.pick("WatcherReply_" + mood, "", allow, False)
        if line is None:
            line = self.dialogue.pick("WatcherReply_Neutral", "", allow, False)
        if line is None:
            return False
        text = personalise(line.text, self.settings)
        return bool(self.speech.say(text=text, priority="normal", event_name="personality.watcher_reply"))

    # ---- the thread ----
    def _loop(self):
        while not self._stop.is_set():
            try:
                if not self.enabled():
                    self._stop.wait(5.0)
                    continue
                if self.seq is None:
                    self.seq = self.client.now_seq()
                wait = 2 if (self.held or self.reply_due) else 20
                answer = self.client.events(self.seq, "voice", wait)
                self.seq = int(answer.get("seq", self.seq))
                for item in answer.get("events", []):
                    self.handle(item)
                self.tick()
            except VoidError as error:
                self.seq = None
                if error.kind != "offline":
                    log.info("Watcher bridge: %s", error.message or error.kind)
                self._stop.wait(OFFLINE_RETRY_SECONDS)
            except Exception:
                log.exception("Watcher bridge problem")
                self._stop.wait(OFFLINE_RETRY_SECONDS)
