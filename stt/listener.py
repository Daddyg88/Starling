"""
The Listener: STARLING's ears.

Three small workers, none of which can slow the game or the journal reader:
  1. the microphone fills a short queue (very light work),
  2. the "ear" thread cuts the sound into sentences (loudness only),
  3. the "brain" thread turns each sentence into text (the heavy part, low priority).

She does NOT act on what she hears while she is speaking (otherwise she would answer herself), and for a moment afterwards (so the end
of her sentence is not mistaken for you). With stt.wake_interrupts on (the default) she keeps ONE ear open for the wake word: a short
phrase heard while she talks is understood, and only if it starts with her name (and is not just her own voice coming back through the
speakers) does she stop talking and listen.

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
BARGE_MAX_SECONDS = 4.0 # while she talks, only short phrases are looked at for her name (a whole sentence is more likely her own voice)
BARGE_GAP = 2.0         # and at most one every two seconds, so understanding speech never competes with her voice for long
BARGE_ECHO_SHARE = 0.7  # if this much of the phrase is words she is saying right now, it is her own voice
SELF_ECHO_SECONDS = 8.0 # a sentence that matches what she just said is her own voice coming back, not you
SELF_ECHO_RATIO = 0.85


def is_garbage(text):
    """Whisper sometimes 'hears' one sound over and over (P-P-P-P-P...). That is never a sentence."""
    words = re.findall(r"[a-z0-9']+", str(text or "").lower())
    if len(words) >= 8 and len(set(words)) <= 2:
        return True
    letters = re.sub(r"[^a-z]", "", str(text or "").lower())
    return len(letters) >= 12 and len(set(letters)) <= 2


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
        self.on_barge = None            # called (no arguments) when you speak over her with her name: it should make her stop talking
        self._last_barge = -1e9

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

    def _barge_on(self):
        return bool(self.settings.get("stt.wake_interrupts", True)) and self.on_barge is not None

    def _mostly_her_words(self, text):
        """True when nearly every word of the phrase is a word she is saying right now: it is her own voice, not you."""
        heard = re.findall(r"[a-z0-9']+", text.lower())
        if not heard:
            return True
        mine = set()
        for _when, said in self._said:
            mine.update(said.split())
        return sum(1 for word in heard if word in mine) / float(len(heard)) >= BARGE_ECHO_SHARE

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
                if self._speaking and not ptt and self._barge_on():
                    try:
                        self._queue(self.detector.feed(frame), False, barge=True)      # she is talking: a short phrase may be you saying her name
                    except Exception:
                        log.exception("Problem while cutting up sound")
                        self.detector.reset()
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

    def _queue(self, utterance, ptt, barge=False):
        if utterance is None:
            return
        if barge:
            if len(utterance) > BARGE_MAX_SECONDS * RATE or self.clock() - self._last_barge < BARGE_GAP:
                return
            self._last_barge = self.clock()
        try:
            self._jobs.put_nowait((utterance, ptt, barge))
        except queue.Full:
            log.debug("Too busy to transcribe; skipped a sentence")

    # ---- the brain ----
    def _think(self):
        while self._running:
            try:
                audio, ptt, barge = self._jobs.get(timeout=0.3)
            except queue.Empty:
                continue
            if self.deaf() and not (barge and self._speaking):
                continue   # she started talking while we were queued: it was probably her
            started = self.clock()
            try:
                text = self.stt.transcribe(audio)
            except Exception:
                log.exception("Transcription failed")
                continue
            took = self.clock() - started
            (log.info if took > 2.5 else log.debug)("Understanding that took %.2f s", took)
            self.handle_text(text, ptt, barge=barge)

    def handle_text(self, text, ptt=False, barge=False):
        text = (text or "").strip()
        if len(text.replace(".", "").strip()) < 2:
            return
        if self._is_her_own_voice(text) or (barge and self._mostly_her_words(text)):
            log.debug("Ignored her own voice: %r", text)
            return
        if is_garbage(text):
            log.debug("Ignored a garbled transcription: %.40r", text)
            return
        wake, command = parse_wake(text, wake_phrase(self.settings))
        if barge:
            if not wake or not self._speaking:
                log.debug("Heard while she was talking, no wake word: ignored")
                return
            log.info("Heard her name while she was talking: she stops and listens (%r)", text)
            self._deaf_until = 0.0
            try:
                self.on_barge()
            except Exception:
                log.exception("Stopping her voice failed")
        self.heard_count += 1
        if wake or ptt or self.settings.get("stt.log_everything", False):
            log.info("Heard: %r (wake=%s)", text, wake)
        else:
            log.debug("Heard (no wake word, %d words)", len(text.split()))
        if self.interceptor is not None:
            try:
                if self.interceptor(text, wake, command, bool(ptt)):
                    return                     # it was an answer to a question she asked, not a command
            except Exception:
                log.exception("The answer checker crashed")
        if self.bus is not None:
            self.bus.publish(HEARD, {"text": text, "wake": wake, "command": command, "ptt": bool(ptt),
                                     "summary": 'You said: "%s"' % text})
