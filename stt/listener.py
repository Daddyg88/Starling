"""
The Listener: STARLING's ears.

Three small workers, none of which can slow the game or the journal reader:
  1. the microphone fills a short queue (very light work),
  2. the "ear" thread cuts the sound into sentences (loudness only),
  3. the "brain" thread turns each sentence into text (the heavy part, low priority).

She does NOT listen while she is speaking (otherwise she would hear herself),
and for a moment afterwards (so the end of her sentence is not mistaken for you).

Each thing you say is announced on the event bus as  "voice.heard"  with:
    text       everything that was understood
    wake       True if you said her name
    command    what came after her name (empty if you only said her name)
    ptt        True if you spoke while holding / after pressing the push-to-talk button
"""

import difflib
import queue
import re
import threading
import time

from core.identity import wake_phrase
from core.logger import get_logger
from stt.vad import RATE, UtteranceDetector
from stt.wake import parse_wake

log = get_logger("listener")

HEARD = "voice.heard"
TAIL_SECONDS = 0.35     # stay deaf this long after she stops talking
SELF_ECHO_SECONDS = 8.0 # a sentence that matches what she just said is her own voice coming back, not you
SELF_ECHO_RATIO = 0.85


class Listener:
    def __init__(self, bus, stt, settings, mic_factory, clock=time.monotonic, gate=None):
        self.bus = bus
        self.stt = stt
        self.settings = settings
        self.mic_factory = mic_factory
        self.gate = gate                # push-to-talk (control/ptt.py), or None
        self._gate_was_open = False
        self.clock = clock
        self.detector = UtteranceDetector(fixed_level=float(settings.get("stt.energy_threshold", 0) or 0),
                                          end_silence_ms=int(settings.get("stt.end_silence_ms", 550) or 550))
        self._jobs = queue.Queue(maxsize=3)
        self._running = False
        self._threads = []
        self._mic = None
        self._speaking = False
        self._deaf_until = 0.0
        self.ready = threading.Event()
        self.failed_reason = ""
        self.heard_count = 0
        self.interceptor = None         # optional: interceptor(text, wake, command, ptt) -> True if it used the sentence
        self._said = []                 # (time, words) of what she said recently

    # ---- lifecycle ----
    def start(self):
        self._running = True
        if self.bus is not None:
            self.bus.subscribe("speech.started", self._on_speech_started)
            self.bus.subscribe("speech.finished", self._on_speech_finished)
        for target, name, daemon in ((self._load_and_listen, "ear", True), (self._think, "brain", True)):
            thread = threading.Thread(target=target, name=name, daemon=daemon)
            thread.start()
            self._threads.append(thread)

    def stop(self):
        self._running = False
        if self.bus is not None:
            self.bus.unsubscribe("speech.started", self._on_speech_started)
            self.bus.unsubscribe("speech.finished", self._on_speech_finished)
        if self._mic is not None:
            self._mic.stop()
        for thread in self._threads:
            thread.join(timeout=3)
        self._threads = []

    # ---- she is talking: do not listen to herself ----
    def _remember_her_words(self, event):
        words = " ".join(re.findall(r"[a-z0-9']+", str(((event.data or {}).get("text")) or "").lower()))
        if words:
            now = self.clock()
            self._said = [(t, w) for t, w in self._said if now - t < SELF_ECHO_SECONDS][-6:] + [(now, words)]

    def _is_her_own_voice(self, text):
        words = " ".join(re.findall(r"[a-z0-9']+", text.lower()))
        now = self.clock()
        for when, said in self._said:
            if now - when > SELF_ECHO_SECONDS + 4:
                continue
            if words and (words in said and len(words) > 12 or difflib.SequenceMatcher(None, words, said).ratio() >= SELF_ECHO_RATIO):
                return True
        return False

    def _on_speech_started(self, event):
        self._remember_her_words(event)
        self._speaking = True
        self.detector.reset()

    def _on_speech_finished(self, _event):
        self._speaking = False
        self._deaf_until = self.clock() + TAIL_SECONDS
        self.detector.reset()

    def deaf(self):
        return self._speaking or self.clock() < self._deaf_until

    # ---- the ear ----
    def _load_and_listen(self):
        try:
            self.stt.load()
            self._mic = self.mic_factory()
            self._mic.start()
        except Exception as error:
            log.exception("Listening could not start")
            self.failed_reason = "Listening could not start: %s" % error
            return
        self.ready.set()
        log.info("Listening.")
        while self._running:
            frame = self._mic.read(0.5)
            if frame is None:
                continue
            ptt = self.gate is not None and self.gate.enabled()
            if self.deaf():
                continue
            try:
                if ptt and not self.gate.is_open():
                    # Button not pressed: ignore the sound, but if it has just been let go, finish the sentence.
                    if self._gate_was_open:
                        self._gate_was_open = False
                        self._queue(self.detector.flush(), True)
                    else:
                        self.detector.learn_noise(frame)
                    continue
                if ptt:
                    self._gate_was_open = True
                elif self._gate_was_open:          # push-to-talk was switched off mid-sentence
                    self._gate_was_open = False
                    self._queue(self.detector.flush(), True)
                utterance = self.detector.feed(frame)
            except Exception:
                log.exception("Problem while cutting up sound")
                self.detector.reset()
                continue
            self._queue(utterance, ptt)

    def _queue(self, utterance, ptt):
        if utterance is None:
            return
        try:
            self._jobs.put_nowait((utterance, ptt))
        except queue.Full:
            log.debug("Too busy to transcribe; skipped a sentence")

    # ---- the brain ----
    def _think(self):
        while self._running:
            try:
                audio, ptt = self._jobs.get(timeout=0.3)
            except queue.Empty:
                continue
            if self.deaf():
                continue   # she started talking while we were queued: it was probably her
            started = self.clock()
            try:
                text = self.stt.transcribe(audio)
            except Exception:
                log.exception("Transcription failed")
                continue
            took = self.clock() - started
            (log.info if took > 1.5 else log.debug)("Understanding that took %.2f s", took)
            self.handle_text(text, ptt)

    def handle_text(self, text, ptt=False):
        text = (text or "").strip()
        if len(text.replace(".", "").strip()) < 2:
            return
        if self._is_her_own_voice(text):
            log.debug("Ignored her own voice: %r", text)
            return
        wake, command = parse_wake(text, wake_phrase(self.settings))
        self.heard_count += 1
        log.info("Heard: %r (wake=%s)", text, wake)
        if self.interceptor is not None:
            try:
                if self.interceptor(text, wake, command, bool(ptt)):
                    return                     # it was an answer to a question she asked, not a command
            except Exception:
                log.exception("The answer checker crashed")
        if self.bus is not None:
            self.bus.publish(HEARD, {"text": text, "wake": wake, "command": command, "ptt": bool(ptt),
                                     "summary": 'You said: "%s"' % text})
