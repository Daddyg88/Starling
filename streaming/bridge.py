"""
Connects the chat sources (Twitch and YouTube) to the rules in streaming/chat.py.

  * a supervisor thread looks at the settings every few seconds: chat on and a channel named -> connect; changed or off -> disconnect
  * a worker thread takes messages from a small queue one at a time (a question can take a few seconds to answer, and
    the chat reader must never wait for that); when the queue is full, extra messages are simply dropped
"""

import queue
import threading
import time

from core.logger import get_logger
from streaming import chat, twitch, youtube

log = get_logger("chat_bridge")

CHECK_SECONDS = 3.0
QUEUE_SIZE = 12


class ChatBridge:
    def __init__(self, settings, director, source_factory=twitch.TwitchChat, clock=time.monotonic,
                 youtube_factory=youtube.YouTubeChat):
        self.settings = settings
        self.director = director
        self.source_factory = source_factory
        self.youtube_factory = youtube_factory
        self.slots = {}
        self.notes = []
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
        """Connects, reconnects or disconnects each platform to match the settings. (Called every few seconds; tests call it directly.)"""
        on = bool(self.settings.get("streaming.enabled", False))
        wanted = {"twitch": twitch.channel_name(self.settings.get("streaming.twitch_channel", "")) if on else "",
                  "youtube": ""}
        key = str(self.settings.get("streaming.youtube_key", "") or "").strip()
        video = youtube.video_id(self.settings.get("streaming.youtube_video", ""))
        if on and key and video:
            wanted["youtube"] = (key, video)
        for platform, want in wanted.items():
            slot = self.slots.get(platform)
            if slot is not None and slot["want"] == want:
                continue
            if slot is not None:
                self._stop_source(slot["source"])
                del self.slots[platform]
            if not want:
                continue
            slot = {"want": want, "status": "Connecting...", "source": None}
            self.slots[platform] = slot
            if platform == "twitch":
                slot["status"] = "Connecting to #%s..." % want
                slot["source"] = self.source_factory(want, self.submit, self._status_setter(platform))
            else:
                slot["status"] = "Connecting to YouTube..."
                slot["source"] = self.youtube_factory(want[0], want[1], self.submit, self._status_setter(platform))
            slot["source"].start()
        self.source = (self.slots.get("twitch") or {}).get("source")
        self.channel = wanted["twitch"]
        self.notes = self._youtube_notes(on, key, self.settings.get("streaming.youtube_video", ""), video)
        self._write_status(on)

    @staticmethod
    def _youtube_notes(on, key, video_text, video):
        """Plain-words hints when YouTube is half set up, so the Streaming page says what is missing."""
        video_text = str(video_text or "").strip()
        if not on or not (key or video_text):
            return []
        if video_text and not video:
            return ["YouTube: that doesn't look like a live stream link (it needs ...watch?v=... or youtu.be/...)"]
        if video and not key:
            return ["YouTube: add your YouTube API key"]
        if key and not video_text:
            return ["YouTube: paste the link of your live stream"]
        if not youtube.looks_like_key(key):
            return ["YouTube: that doesn't look like an API key (about 39 letters and numbers, starting AIza)"]
        return []

    def _status_setter(self, platform):
        def set_status(text):
            slot = self.slots.get(platform)
            if slot is not None:
                slot["status"] = text
                self._write_status(True)
        return set_status

    def _write_status(self, on):
        parts = []
        if len(self.slots) == 1 and not self.notes:
            parts = [next(iter(self.slots.values()))["status"]]
        else:
            parts = ["%s: %s" % ("Twitch" if name == "twitch" else "YouTube", slot["status"]) for name, slot in self.slots.items()]
            parts += [note for note in self.notes if not note.startswith("YouTube") or "youtube" not in self.slots]
        if not parts:
            text = "Off" if not on else "Chat is on: type your Twitch channel name or add your YouTube key and link"
        else:
            text = " | ".join(parts)
        # YouTube flips between "Looking for the live chat..." and "no live chat right now" every 30 s while you are not live: log that once
        shown = text.replace("Looking for the live chat...", "That video has no live chat right now. Waiting for the stream to go live...")
        if shown != getattr(self, "logged_text", None):
            log.info("Streaming: %s", text)
            self.logged_text = shown
        self.state_text = text

    def _stop_source(self, source):
        if source is not None:
            try:
                source.stop()
            except Exception:
                log.exception("Could not stop the chat reader")

    def _disconnect(self):
        for slot in list(self.slots.values()):
            self._stop_source(slot["source"])
        self.slots = {}
        self.source = None
        self.channel = ""

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
                self._pump()
                continue
            try:
                self.director.handle(message)
                self._pump()
            except Exception:
                log.exception("Chat message failed")

    def _pump(self):
        try:
            self.director.pump()
        except Exception:
            log.exception("Answering a held chat question failed")

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
