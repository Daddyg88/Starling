"""
Connects the chat sources (Twitch now, YouTube later) to the rules in streaming/chat.py.

  * a supervisor thread looks at the settings every few seconds: chat on and a channel named -> connect; changed or off -> disconnect
  * a worker thread takes messages from a small queue one at a time (a question can take a few seconds to answer, and
    the chat reader must never wait for that); when the queue is full, extra messages are simply dropped
"""

import queue
import threading
import time

from core.logger import get_logger
from streaming import chat, twitch

log = get_logger("chat_bridge")

CHECK_SECONDS = 3.0
QUEUE_SIZE = 12


class ChatBridge:
    def __init__(self, settings, director, source_factory=twitch.TwitchChat, clock=time.monotonic):
        self.settings = settings
        self.director = director
        self.source_factory = source_factory
        self.clock = clock
        self.queue = queue.Queue(maxsize=QUEUE_SIZE)
        self.source = None
        self.channel = ""
        self.state_text = "Off"
        self._stop = threading.Event()
        self._threads = []

    # ---- what the dashboard shows ----
    def status(self):
        return self.state_text

    def recent(self, limit=12):
        """Lines like 'Gav: !lights -> done' (newest last)."""
        lines = []
        for r in list(self.director.log)[-limit:]:
            what = r.text if r.kind == "action" else (r.text[:60] + ("..." if len(r.text) > 60 else ""))
            lines.append("%s: %s -> %s%s" % (r.user, what, r.status, (" (%s)" % r.note) if r.note else ""))
        return lines

    # ---- life ----
    def start(self):
        if self._threads:
            return
        for target, name in ((self._supervise, "chat-supervisor"), (self._work, "chat-worker")):
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self._threads.append(thread)

    def stop(self):
        self._stop.set()
        self._disconnect()

    def _supervise(self):
        while not self._stop.is_set():
            try:
                self.check()
            except Exception:
                log.exception("Chat settings check failed")
            self._stop.wait(CHECK_SECONDS)

    def check(self):
        """Connects, reconnects or disconnects to match the settings. (Called every few seconds; tests call it directly.)"""
        wanted = twitch.channel_name(self.settings.get("streaming.twitch_channel", "")) if self.settings.get("streaming.enabled", False) else ""
        if wanted == self.channel and (self.source is not None or not wanted):
            if not wanted:
                self.state_text = "Off" if not self.settings.get("streaming.enabled", False) else "Chat is on: type your Twitch channel name"
            return
        self._disconnect()
        self.channel = wanted
        if not wanted:
            self.state_text = "Off" if not self.settings.get("streaming.enabled", False) else "Chat is on: type your Twitch channel name"
            return
        self.state_text = "Connecting to #%s..." % wanted
        self.source = self.source_factory(wanted, self.submit, self._set_status)
        self.source.start()

    def _set_status(self, text):
        self.state_text = text

    def _disconnect(self):
        source, self.source = self.source, None
        self.channel = ""
        if source is not None:
            try:
                source.stop()
            except Exception:
                log.exception("Could not stop the chat reader")

    # ---- messages ----
    def submit(self, message):
        try:
            self.queue.put_nowait(message)
        except queue.Full:
            pass                                      # a flood: drop it

    def _work(self):
        while not self._stop.is_set():
            try:
                message = self.queue.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                self.director.handle(message)
            except Exception:
                log.exception("Chat message failed")

    def pretend(self, user, text, mod=False, sub=False, owner=False, done=None):
        """The dashboard's test box: runs a made-up message through the same rules, even when chat is switched off."""
        def go():
            try:
                result = self.director.handle(chat.ChatMessage("test", user or "Tester", text, mod=mod, sub=sub, owner=owner), test=True)
            except Exception:
                log.exception("The chat test failed")
                result = chat.Result("failed", user=user, note="see the log")
            if done is not None:
                done(result)
        threading.Thread(target=go, name="chat-test", daemon=True).start()
