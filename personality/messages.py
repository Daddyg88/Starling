"""
MESSAGE READER: she reads your incoming chat messages out loud, but only when nothing else is happening.

Elite writes every message you receive to the journal (ReceiveText: who, what, and which channel). They wait in a
short queue and she says them one at a time when it is calm: she is not talking or asking you something, no safety
warning in the last 30 seconds, and the ship is not jumping, in danger, overheating, low on fuel or has weapons out.
A message that has waited more than 3 minutes is dropped (it would be old news), and the queue keeps the newest 6.

Settings: messages.read (on/off), messages.channels (direct = direct messages only, the default; direct_plus = also friends,
wing, squadron and multicrew; all = also local and system chat) and messages.npc (also read computer-controlled ships and stations, off by default).
Her lines are in voicepacks/default/messages.json.
"""

import re
import threading
import time
from collections import deque

from core.identity import personalise
from core.logger import get_logger
from personality.mood_engine import effective_mood
from personality.watcher import BUSY_BITS, CALM_AFTER_CRITICAL_SECONDS

log = get_logger("messages")

PLAYER_CHANNELS = {"wing", "local", "voicechat", "friend", "player", "squadron", "starsystem", "multicrew"}
# messages.channels: which player chat she reads ("npc" has its own switch). Elite's channel "player" is a DIRECT message.
CHANNEL_SETS = {
    "direct": {"player"},
    "direct_plus": {"player", "friend", "wing", "squadron", "multicrew", "voicechat"},
    "all": PLAYER_CHANNELS,
}
MAX_WAITING = 6
STALE_SECONDS = 180.0
MAX_CHARS = 220
_URL = re.compile(r"https?://\S+|www\.\S+", re.I)
_MARKUP = re.compile(r"<[^>]*>|\$[A-Za-z0-9_:#=;]+;?")


def tidy(text):
    text = _MARKUP.sub(" ", str(text or ""))
    text = _URL.sub("a link", text)
    text = " ".join(text.split())
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rsplit(" ", 1)[0] + "..."
    return text


def tidy_name(name):
    name = _MARKUP.sub(" ", str(name or "")).strip()
    return " ".join(name.split()).removeprefix("CMDR ").removeprefix("Cmdr ").strip()


class MessageReader:
    def __init__(self, bus, speech, dialogue, settings, state_provider=None, ask_provider=None, clock=time.monotonic):
        self.bus = bus
        self.speech = speech
        self.dialogue = dialogue
        self.settings = settings
        self.state_provider = state_provider or (lambda: None)
        self.ask_provider = ask_provider or (lambda: None)
        self.clock = clock
        self.queue = deque(maxlen=MAX_WAITING)       # (name, message, channel, time)
        self._last_critical = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    # ---- wiring ----
    def attach(self):
        self.bus.subscribe("*", self.on_event)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="message-reader", daemon=True)
        self._thread.start()

    def detach(self):
        self.bus.unsubscribe("*", self.on_event)
        self._stop.set()
        self._thread = None

    def enabled(self):
        return bool(self.settings.get("messages.read", True) and self.settings.get("speech.enabled", True))

    # ---- hearing about messages ----
    def on_event(self, event):
        if getattr(event, "priority", "") == "critical":
            self._last_critical = self.clock()
        if getattr(event, "name", "") != "ReceiveText" or not self.enabled():
            return
        data = event.data or {}
        channel = str(data.get("Channel") or "").lower()
        if channel == "npc" and not self.settings.get("messages.npc", False):
            return
        allowed = CHANNEL_SETS.get(str(self.settings.get("messages.channels", "direct")), CHANNEL_SETS["direct"])
        if channel != "npc" and channel not in allowed:
            return
        message = tidy(data.get("Message_Localised") or data.get("Message"))
        name = tidy_name(data.get("From_Localised") or data.get("From"))
        if not message:
            return
        with self._lock:
            self.queue.append((name, message, channel, self.clock()))

    # ---- is it a calm moment? ----
    def calm(self):
        if self._last_critical is not None and self.clock() - self._last_critical < CALM_AFTER_CRITICAL_SECONDS:
            return False
        if self.speech is not None and self.speech.is_busy():
            return False
        ask = self.ask_provider()
        if ask is not None and getattr(ask, "pending", None) is not None:
            return False
        state = self.state_provider()
        flags = getattr(state, "status_flags", 0) if state is not None else 0
        return not any((flags >> bit) & 1 for bit in BUSY_BITS)

    # ---- saying one ----
    def tick(self):
        """Say the oldest message that is still fresh, if it is calm. Returns True if she spoke."""
        if not self.enabled():
            with self._lock:
                self.queue.clear()
            return False
        with self._lock:
            now = self.clock()
            while self.queue and now - self.queue[0][3] > STALE_SECONDS:
                self.queue.popleft()
            if not self.queue or not self.calm():
                return False
            name, message, channel, _t = self.queue.popleft()
        return self._say(name, message, channel)

    def _say(self, name, message, channel):
        if self.speech is None or self.dialogue is None:
            return False
        key = "MessageIn_" + (channel if channel in PLAYER_CHANNELS | {"npc"} else "local")
        if not name:
            key += "_Anonymous"
        mood = "" if self.settings.get("personality.style", "personality") == "info" else (effective_mood(self.settings) or "")
        line = self.dialogue.pick(key, mood, bool(self.settings.get("speech.allow_mature", False)), False)
        if line is None:
            line = self.dialogue.pick("MessageIn_local", mood, False, False)
        if line is None:
            return False
        try:
            text = line.text.format_map(_Fields(name=name, message=message))
        except (ValueError, IndexError):
            text = "%s says: %s" % (name or "Someone", message)
        return bool(self.speech.say(text=personalise(text, self.settings), priority="normal", event_name="personality.message"))

    def _loop(self):
        while not self._stop.wait(2.0):
            try:
                self.tick()
            except Exception:
                log.exception("Message reader problem")


class _Fields(dict):
    def __missing__(self, key):
        return ""
