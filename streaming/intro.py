"""THE STREAM INTRO: "start ten minute intro".

You say it before you go live. For the next few minutes she plays at "having to get ready" (fixing her hair, checking her make-up in a little mirror,
straightening her collar, looking for her cup...) while she talks to your viewers. Plain Python and no network: all of it is tested.

    say "start ten minute intro"      she says a short line, then keeps quiet for a minute (streaming.intro_wait)
    after that, until the time is up  she answers EVERY chat message (not only !starling ones), one at a time, by name, still pretending to
                                      get ready; when chat is quiet she grumbles about getting ready on her own now and then
    then                              "right, I'm ready" and she is back to normal
    say "stop the intro" or "I'm ready"   ends it at once, at any time

The replies are written by the local AI chat model when it is installed (Settings > Personality > AI chat). If it is not, or it is too slow, or it
gives an unusable answer, she says one of her ordinary lines from voicepacks/default/streaming.json (StreamIntro_*) instead, so she never goes silent.
Chat is filtered exactly like her other chat answers (blocked words, links, very long messages, bots), and it needs stream chat to be switched on.
Commands like !lights and !starling <question> are NOT taken over: they go through the normal chat rules.
"""

import random
import re
import time
from collections import deque

from core.logger import get_logger
from streaming import chat as stream_chat

log = get_logger("stream_intro")

WAIT_SECONDS = 60.0          # quiet time after the command, before the "getting ready" chat starts (streaming.intro_wait)
TOTAL_MINUTES = 10           # the whole intro (streaming.intro_minutes); the chat part is this minus the wait, minus a minute to finish
FINISH_SECONDS = 60.0        # kept at the end so the last reply is not cut off by "I'm ready"
REPLY_GAP = 4.0              # at least this long between two replies
FILLER_GAP = (45.0, 75.0)    # when chat is quiet she talks about getting ready by herself this often
MAX_AGE = 90.0               # a message that waited longer than this is dropped (she is behind: better to answer the new ones)
MAX_WAITING = 8
HISTORY = 12                 # chat lines she can "see" when she answers
MAX_TEXT = 140
MIN_MINUTES, MAX_MINUTES = 3, 30

ACTIVITIES = (
    "fixing my hair", "checking my make-up in the little mirror", "straightening my collar", "tugging my sleeves straight",
    "looking for my lucky cup", "warming up my voice", "dusting off my emitter", "testing the lights", "stretching my arms",
    "practising my best smile", "finding my other glove", "untangling a cable", "smoothing out my suit", "waiting for my hair to behave",
    "hunting for my notes", "checking my reflection one more time", "trying to look natural", "fussing over my collar",
)
BOT_NAMES = ("nightbot", "streamelements", "streamlabs", "moobot", "fossabot", "wizebot", "soundalerts", "commanderroot", "sery_bot")

SYSTEM = ("You are Starling MoonFox, a cheeky hologram AI companion, live on a stream talking to the Commander's viewers in chat. "
          "Right now you are pretending that you have to get ready before the stream starts, and at this moment you are {activity}. "
          "Answer {name}'s chat message with ONE short sentence of 6 to 20 words, spoken aloud, in character: playful, a little flustered about "
          "getting ready, warm and funny. Start with their name. Only sometimes mention what you are doing. "
          "Never say you are an AI model or an assistant, never give links, never repeat rude words or insults from chat, never make promises, "
          "no emojis, no lists, no stage directions. If you do not know something, joke about being busy getting ready. {seen}")

WORD_NUMBERS = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
                "twenty": 20, "thirty": 30}


def spoken(name):
    return stream_chat.spoken_name(name)


class StreamIntro:
    """say_key(key, fields), say_text(text): her voice. ask_llm(messages) -> text or None. free() -> True when she may speak.
    publish(event_name): tells the hologram (so she plays a 'getting ready' clip)."""

    def __init__(self, settings, say_key, say_text, ask_llm=None, free=None, publish=None, clock=time.monotonic, rng=None):
        self.settings = settings
        self.say_key, self.say_text, self.ask_llm = say_key, say_text, ask_llm
        self.free = free or (lambda: True)
        self.publish = publish or (lambda name: None)
        self.clock = clock
        self.rng = rng or random.Random()
        self.state = "off"                       # off, waiting (the quiet minute) or active
        self.active_from = self.ends_at = 0.0
        self.queue = deque()                     # (time, user, text) waiting for an answer
        self.seen = deque(maxlen=HISTORY)        # (user, text) the chat she can see
        self.history = deque(maxlen=3)           # her last few exchanges, for the AI
        self.last_spoke = 0.0
        self.next_filler = 0.0
        self.activity = ""
        self.used_ai = 0
        self.used_lines = 0

    # ---- settings ----
    def option(self, name, default):
        return self.settings.get("streaming." + name, default)

    def _number(self, name, default):
        try:
            return float(self.option(name, default))
        except (TypeError, ValueError):
            return float(default)

    @property
    def running(self):
        return self.state != "off"

    # ---- start and stop ----
    def start(self, minutes=None):
        """Begin. Returns 'started', 'running' (already on) or 'off' (stream chat is switched off, so nobody could be answered)."""
        if self.running:
            return "running"
        if not self.option("enabled", False):
            return "off"
        now = self.clock()
        total = minutes if minutes else self._number("intro_minutes", TOTAL_MINUTES)
        total = max(MIN_MINUTES, min(MAX_MINUTES, float(total)))
        wait = max(5.0, min(300.0, self._number("intro_wait", WAIT_SECONDS)))
        self.state = "waiting"
        self.active_from = now + wait
        self.ends_at = max(self.active_from + 60.0, now + total * 60.0 - FINISH_SECONDS)
        self.queue.clear()
        self.history.clear()
        self.last_spoke = now
        self.next_filler = self.active_from + self.rng.uniform(*FILLER_GAP)
        self.activity = ""
        self.used_ai = self.used_lines = 0
        log.info("Stream intro started: %.0f minutes in all", total)
        return "started"

    def cancel(self):
        if not self.running:
            return False
        self.state = "off"
        self.queue.clear()
        log.info("Stream intro stopped (%d AI replies, %d ordinary lines)", self.used_ai, self.used_lines)
        return True

    # ---- chat comes in ----
    def offer(self, message):
        """True when the intro took this chat message (it will answer it, or quietly drop it); False means the normal chat rules should see it."""
        if not self.running or not isinstance(message, stream_chat.ChatMessage):
            return False
        if stream_chat.parse(message.text, self.option("prefix", stream_chat.DEFAULT_PREFIX)) is not None:
            return False                                           # !starling questions and !lights go the normal way
        text = stream_chat.tidy(message.text)
        user = stream_chat.clean_name(message.user)
        if not text or text.startswith("!") or len(text) > MAX_TEXT:
            return True
        low = user.lower()
        if low in BOT_NAMES or low.endswith("bot"):
            return True
        if re.search(r"https?://|www\.|\.com\b", text) or stream_chat.has_blocked_word(text, stream_chat.split_words(self.option("blocked_words", ""))):
            return True
        self.seen.append((user, text))
        self.queue.append((self.clock(), user, text))
        while len(self.queue) > MAX_WAITING:
            self.queue.popleft()
        return True

    # ---- the clock ----
    def pump(self):
        """Call about once a second. Returns what it did: '', 'began', 'replied', 'filler' or 'ended' (tests use this)."""
        if not self.running:
            return ""
        now = self.clock()
        if self.state == "waiting":
            if now < self.active_from:
                return ""
            self.state = "active"
            self.next_filler = now + self.rng.uniform(*FILLER_GAP)
            self._say_line("StreamIntro_Begin", {})
            self.last_spoke = now
            self.publish("IntroGettingReady")
            return "began"
        if now >= self.ends_at:
            self.state = "off"
            self.queue.clear()
            self._say_line("StreamIntro_End", {})
            self.publish("IntroGettingReady")
            return "ended"
        if not self.free() or now - self.last_spoke < REPLY_GAP:
            return ""
        while self.queue and now - self.queue[0][0] > MAX_AGE:
            self.queue.popleft()
        if self.queue:
            _, user, text = self.queue.popleft()
            self._reply(user, text)
            self.last_spoke = self.clock()
            return "replied"
        if now >= self.next_filler:
            self._say_line("StreamIntro_Filler", {})
            self.last_spoke = now
            self.next_filler = now + self.rng.uniform(*FILLER_GAP)
            self.publish("IntroGettingReady")
            return "filler"
        return ""

    # ---- saying things ----
    def _new_activity(self):
        options = [a for a in ACTIVITIES if a != self.activity]
        self.activity = self.rng.choice(options)
        return self.activity

    def _say_line(self, key, fields):
        fields = dict(fields)
        fields.setdefault("activity", self._new_activity())
        try:
            self.say_key(key, fields)
        except Exception:
            log.exception("A stream intro line could not be said")

    def _messages(self, user, text):
        names = ", ".join("%s: %s" % (spoken(u), t) for u, t in list(self.seen)[-6:-1])
        seen = ("The latest chat before this: %s." % names) if names else ""
        system = SYSTEM.format(activity=self.activity or self._new_activity(), name=spoken(user), seen=seen)
        messages = [{"role": "system", "content": system}]
        for said, answered in self.history:
            messages.append({"role": "user", "content": said})
            messages.append({"role": "assistant", "content": answered})
        messages.append({"role": "user", "content": "%s: %s" % (spoken(user), text)})
        return messages

    def _reply(self, user, text):
        self._new_activity()
        answer = None
        if self.ask_llm is not None and self.option("intro_ai", True):
            try:
                answer = self.ask_llm(self._messages(user, text))
            except Exception:
                log.exception("The AI chat model failed during the stream intro")
                answer = None
        if answer:
            first = spoken(user).split(" ")[0].lower()
            if first not in answer.lower():
                answer = "%s, %s" % (spoken(user), answer[:1].lower() + answer[1:])
            try:
                self.say_text(answer)
            except Exception:
                log.exception("A stream intro reply could not be said")
            self.history.append(("%s: %s" % (spoken(user), text), answer))
            self.used_ai += 1
        else:
            self._say_line("StreamIntro_Reply", {"user": spoken(user), "activity": self.activity})
            self.used_lines += 1
        if self.rng.random() < 0.5:
            self.publish("IntroGettingReady")


# ---- the voice commands ----
_START_VERB = r"(?:start|begin|run|do|launch|play|kick off|open)"
_START = re.compile(r"\b%s\b.*\b(?:intro|opener|intro mode)\b|\b%s\b.*\b(?:minute|minit|min)\b" % (_START_VERB, _START_VERB))
_STOP = re.compile(r"^(?:(?:please )?(?:stop|cancel|end|skip|abort|finish|quit) (?:the |my )?(?:stream )?(?:intro|opener)(?: now)?|"
                   r"(?:(?:okay|ok|right|alright) )?(?:i am|im|i'm) ready(?: now)?|(?:okay|ok|right|alright)?\s*that will do(?: now)?|"
                   r"(?:i am|im) (?:live|going live)(?: now)?|go live)$")
_MINUTES = re.compile(r"\b(\d{1,2}|%s)\s*(?:minute|minit|min|minutes)\b" % "|".join(WORD_NUMBERS))


def minutes_in(said):
    """The length in minutes named in a spoken sentence ('start a five minute intro' -> 5), or None."""
    found = _MINUTES.search(said)
    if not found:
        return None
    word = found.group(1)
    return int(word) if word.isdigit() else WORD_NUMBERS.get(word)


class IntroVoice:
    """Voice commands for the intro. Only clear phrases count; "I'm ready" and "stop the intro" do nothing unless an intro is running."""

    def __init__(self, intro_provider, narrator=None):
        self.intro_provider = intro_provider
        self.narrator = narrator

    def _say(self, key):
        if self.narrator is not None:
            try:
                self.narrator.say(key)
            except Exception:
                log.exception("The intro voice line failed")

    def try_handle(self, text):
        said = re.sub(r"[^a-z0-9' ]", " ", str(text or "").lower())
        said = re.sub(r"\s+", " ", said).strip()
        if not said or len(said) > 80:
            return None
        starting = bool(_START.search(said)) and "intro" in said
        wants_stop = bool(_STOP.search(said))
        if not (starting or wants_stop):
            return None
        intro = self.intro_provider()
        if intro is None:
            return None
        if wants_stop:
            if not intro.cancel():
                return None                                      # nothing is running: it is an ordinary sentence
            self._say("StreamIntro_Cancel")
            return "Stream intro stopped."
        result = intro.start(minutes_in(said))
        if result == "started":
            self._say("StreamIntro_Start")
            return "Stream intro started."
        if result == "running":
            self._say("StreamIntro_Already")
            return "The stream intro is already running."
        self._say("StreamIntro_NoChat")
        return "Stream chat is off, so nobody could talk to me."
