"""
The SpeechManager: STARLING's mouth.

Everything that wants her to say something goes through here. She talks from
ONE background thread, so lines never overlap and nothing freezes while she speaks.

Rules (these keep her useful instead of annoying):
  * CRITICAL lines jump the queue and cut off anything less important.
  * Ordinary lines wait their turn, but are dropped if they get too old
    (nobody wants to hear about a docking 20 seconds late).
  * LOW lines are dropped if she is already busy.
  * The queue is short, so she never falls minutes behind.
  * If a recording is missing or fails, the text goes to the local cloned voice (Kokoro).
    The old Windows voice (Hazel) is only used if speech.windows_emergency_voice is true.
"""

import itertools
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from core.logger import get_logger
from tts.base_tts import VoiceSettings

log = get_logger("speech")

_RANK = {"critical": 0, "normal": 1, "low": 2}
DEFAULT_MAX_AGE = {"critical": 30.0, "normal": 8.0, "low": 4.0}
MAX_WAITING_NORMAL = 3


@dataclass
class SpeechItem:
    text: Optional[str]
    audio_path: Optional[object]
    speak_text_after: bool
    after_text: Optional[str]
    priority: str
    event_name: str
    created: float
    seq: int = 0
    cancelled: bool = field(default=False)


class SpeechManager:
    def __init__(self, providers, settings, bus=None, max_age=None, clock=time.monotonic):
        self.providers = providers
        self.settings = settings
        self.bus = bus
        self.max_age = dict(DEFAULT_MAX_AGE if max_age is None else max_age)
        self.clock = clock
        self._queue = []
        self._cond = threading.Condition()
        self._current = None
        self._current_providers = []
        self._thread = None
        self._running = False
        self._counter = itertools.count()
        self._warned_no_voice = False
        self.dropped = 0

    # ---- lifecycle ----
    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run, name="speech", daemon=True)
        self._thread.start()

    def stop(self):
        with self._cond:
            self._running = False
            for item in self._queue:
                item.cancelled = True
            self._queue.clear()
            self._cancel_current()
            self._cond.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=3)

    # ---- asking her to speak ----
    def say(self, text=None, audio_path=None, speak_text_after=False,
            priority="normal", event_name="", after_text=None):
        """Queue a line. Returns True if it was accepted, False if dropped."""
        if priority not in _RANK:
            priority = "normal"
        if not text and not audio_path:
            return False
        item = SpeechItem(text, audio_path, speak_text_after, after_text, priority, event_name,
                          self.clock(), next(self._counter))
        with self._cond:
            if not self._running:
                return False
            if priority == "low" and (self._current is not None or self._queue):
                self.dropped += 1
                return False
            if priority == "critical":
                # Anything less important that is waiting is no longer worth saying.
                kept = [q for q in self._queue if q.priority == "critical"]
                self.dropped += len(self._queue) - len(kept)
                self._queue[:] = kept
                if self._current is not None and self._current.priority != "critical":
                    self._cancel_current()
            elif priority == "normal":
                waiting = [q for q in self._queue if q.priority == "normal"]
                if len(waiting) >= MAX_WAITING_NORMAL:
                    self._queue.remove(waiting[0])  # drop the oldest
                    self.dropped += 1
            self._queue.append(item)
            self._cond.notify_all()
        return True

    def interrupt(self):
        """Stop talking now, unless she is saying a safety warning. Used when you press the push-to-talk button."""
        with self._cond:
            kept = [q for q in self._queue if q.priority == "critical"]
            self.dropped += len(self._queue) - len(kept)
            self._queue[:] = kept
            if self._current is not None and self._current.priority != "critical":
                self._cancel_current()
                return True
        return False

    def is_busy(self):
        with self._cond:
            return self._current is not None or bool(self._queue)

    def wait_until_idle(self, timeout=30.0):
        """Block until nothing is being said or waiting. Handy for tests."""
        deadline = time.monotonic() + timeout
        with self._cond:
            while (self._current is not None or self._queue) and time.monotonic() < deadline:
                self._cond.wait(0.05)
            return self._current is None and not self._queue

    # ---- the speaking thread ----
    def _cancel_current(self):
        """Cut off whatever is being said now. Caller must hold the lock."""
        if self._current is not None:
            self._current.cancelled = True
            for provider in self._current_providers:
                provider.stop()

    def _next_item(self):
        with self._cond:
            while self._running and not self._queue:
                self._cond.wait(0.5)
            if not self._running:
                return None
            self._queue.sort(key=lambda q: (_RANK[q.priority], q.seq))
            item = self._queue.pop(0)
            self._current = item
            return item

    def _run(self):
        log.info("Speech thread started")
        while self._running:
            item = self._next_item()
            if item is None:
                break
            try:
                age = self.clock() - item.created
                if item.priority != "critical" and age > self.max_age.get(item.priority, 8.0):
                    self.dropped += 1
                    log.debug("Dropped a stale line for %s (%.1fs old)", item.event_name, age)
                else:
                    self._speak(item)
            except Exception:
                log.exception("Problem while speaking")
            finally:
                with self._cond:
                    self._current = None
                    self._current_providers = []
                    self._cond.notify_all()
        log.info("Speech thread stopped")

    def text_provider(self):
        """The text-to-speech provider chosen in settings (normally the cloned Kokoro voice)."""
        wanted = self.settings.get("tts.provider", "kokoro")
        emergency = self.settings.get("speech.windows_emergency_voice", False)
        # An old settings.json may still say "windows". Hazel is retired, so that now means Kokoro.
        names = [wanted] if (wanted != "windows" or emergency) else []
        names.append("kokoro")
        if emergency:
            names.append("windows")   # opt-in last resort only
        for name in names:
            provider = self.providers.get(name)
            if provider is not None and provider.available()[0]:
                return provider
        return None

    def _use(self, provider):
        with self._cond:
            self._current_providers = [provider]
            if self._current is not None and self._current.cancelled:
                provider.stop()  # an interrupt arrived just before we started

    def _speak(self, item):
        voice = VoiceSettings.from_settings(self.settings)
        if item.text:
            log.info("Said [%s]: %s", item.event_name or "?", item.text.replace("||", " ")[:160])     # so a log shows every line, for spotting repeats
        self._announce("speech.started", item)
        spoke = False

        if item.audio_path and self.settings.get("speech.use_recordings", True):
            recorded = self.providers.get("recorded")
            if recorded is not None and recorded.available()[0] and not item.cancelled:
                self._use(recorded)
                spoke = recorded.speak("", voice, item.audio_path)
                if not spoke and not item.cancelled:
                    log.warning("Could not play %s; using the cloned voice instead", item.audio_path)

        if spoke:
            follow = item.after_text or (item.text if item.speak_text_after else None)
        else:
            follow = item.text
        if follow and not item.cancelled:
            provider = self.text_provider()
            if provider is None:
                if not self._warned_no_voice:
                    self._warned_no_voice = True
                    log.error("No voice is available, so STARLING cannot speak. Run run_voice_test.bat")
            else:
                self._use(provider)
                if provider.name != "kokoro":
                    follow = follow.replace("||", " ")   # only the cloned voice knows about beats
                provider.speak(follow, voice)

        self._announce("speech.finished", item)

    def _announce(self, name, item):
        if self.bus is not None:
            path = item.audio_path
            self.bus.publish(name, {
                "text": (item.text or "").replace("||", " "),
                "audio": getattr(path, "name", "") if path else "",
                "event": item.event_name,
            }, "low")
