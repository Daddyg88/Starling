"""
The RULES for stream chat. Plain Python, no network, no game: everything here is tested.

A viewer's message is one of three things:
    !starling what is a neutron star?     a question (she answers out loud)
    !lights  /  !starling night vision    one of the few actions on the list below
    anything else                         ignored

Safety, in the order it is checked:
  1. Chat is OFF unless the streamer switched it on.
  2. Only messages that start with the prefix (default !starling) or a ! command from the list below are looked at.
  3. Who may use it: everyone, subscribers or moderators (the streamer always can).
  4. Blocked words, links and very long messages are dropped.
  5. Cooldowns: one thing per viewer every N seconds, and a gap between actions and between questions overall.
  6. Actions must be switched on by the streamer AND safe right now (see action_blocker).
Chat text is NEVER treated as a free-form command. An action only happens when it matches the list exactly.
"""

import re
import unicodedata
from collections import deque
from dataclasses import dataclass

DEFAULT_PREFIX = "!starling"
MAX_QUESTION = 140
MAX_NAME = 25

# Status.json flag bits (see journal/status_reader.py)
DOCKED, LANDED, SUPERCRUISE, MASS_LOCKED, FSD_CHARGING, LAT_LONG, IN_DANGER, IN_MAIN_SHIP, FSD_JUMP = 0, 1, 4, 16, 17, 21, 22, 24, 30


@dataclass(frozen=True)
class ChatAction:
    key: str                  # also the settings name: streaming.act_<key>
    label: str                # how she says it
    phrase: str               # what is handed to her normal voice-command code (so only the player's own keys are ever pressed)
    aliases: tuple            # what a viewer can type after the !
    default_on: bool
    risky: bool = False       # gets extra checks (see action_blocker)
    help: str = ""


ACTIONS = (
    ChatAction("lights", "the ship lights", "toggle the ship lights", ("lights", "light", "spotlight"), True,
               help="Flips your ship lights"),
    ChatAction("night_vision", "night vision", "toggle night vision", ("nightvision", "night", "nv"), True,
               help="Flips night vision"),
    ChatAction("head_look", "head look", "toggle head look", ("headlook", "look"), False,
               help="Flips head look on or off. Can be annoying if chat spams it"),
    ChatAction("scoop", "the cargo scoop", "toggle the cargo scoop", ("scoop", "cargoscoop"), False,
               help="Opens or closes the cargo scoop"),
    ChatAction("gear", "the landing gear", "toggle the landing gear", ("gear", "wheels", "landinggear"), False, risky=True,
               help="Landing gear. Only works in normal space, away from planets, stations and anything big (mass lock)"),
)
BY_KEY = {a.key: a for a in ACTIONS}
BY_ALIAS = {alias: a for a in ACTIONS for alias in a.aliases}


@dataclass
class ChatMessage:
    platform: str             # "twitch" or "youtube"
    user: str
    text: str
    mod: bool = False
    sub: bool = False
    owner: bool = False


def clean_name(name):
    """A name that is safe to say out loud: letters, digits, underscores and spaces only."""
    name = re.sub(r"[^A-Za-z0-9_ ]", "", str(name or "")).strip()
    return name[:MAX_NAME] or "someone"


_EMOTICON = re.compile(r"(?:(?<=\s)|^)[:;=][-']?[)(DPpOo3/\\|]+(?=\s|$)")


def tidy(text):
    """One tidy line: no control characters, no emoji and no :D style faces (she would read them out loud)."""
    text = re.sub(r"[\x00-\x1f\x7f]", " ", str(text or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) not in ("So", "Cs", "Co", "Cn"))
    text = _EMOTICON.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse(text, prefix=DEFAULT_PREFIX):
    """('ask', question) or ('action', key) or None."""
    text = tidy(text)
    prefix = (tidy(prefix) or DEFAULT_PREFIX).lower()
    low = text.lower()
    if low == prefix or low.startswith(prefix + " ") or low.startswith(prefix + ",") or low.startswith(prefix + ":"):
        rest = text[len(prefix):].lstrip(" ,:-")
        if not rest:
            return None
        squashed = re.sub(r"[^a-z]", "", rest.lower())              # "night vision" -> "nightvision"
        if len(rest.split(" ")) <= 2 and squashed in BY_ALIAS:
            return ("action", BY_ALIAS[squashed].key)
        return ("ask", rest)
    if text.startswith("!") and len(text) > 1:
        word = re.sub(r"[^a-z]", "", text[1:].split(" ")[0].lower())
        if word in BY_ALIAS and len(text.split(" ")) <= 3:
            return ("action", BY_ALIAS[word].key)
    return None


def has_blocked_word(text, blocked):
    low = " " + re.sub(r"[^a-z0-9 ]", " ", str(text or "").lower()) + " "
    low = re.sub(r"\s+", " ", low)
    for word in blocked:
        word = re.sub(r"[^a-z0-9 ]", "", word.lower()).strip()
        if word and (" %s " % word) in low:
            return True
    return False


def split_words(raw):
    return [w.strip() for w in re.split(r"[,;\n]", str(raw or "")) if w.strip()][:100]


def flag(state, bit):
    flags = getattr(state, "status_flags", None)
    return bool(flags is not None and (int(flags) >> bit) & 1)


def action_blocker(action, state):
    """None when it is safe to do this now, otherwise a short reason."""
    if state is None or getattr(state, "game_quit", False):
        return "the game isn't running"
    if getattr(state, "gui_focus", 0):
        return "a menu is open"
    if not flag(state, IN_MAIN_SHIP):
        return "not in the ship"
    if flag(state, FSD_JUMP):
        return "mid-jump"
    if action.risky:
        if flag(state, DOCKED) or flag(state, LANDED):
            return "docked or landed"
        if flag(state, SUPERCRUISE):
            return "in supercruise"
        if flag(state, MASS_LOCKED) or flag(state, LAT_LONG) or getattr(state, "latitude", None) is not None:
            return "too close to something big"
        if flag(state, IN_DANGER):
            return "in danger"
    return None


class Cooldowns:
    def __init__(self, clock):
        self.clock = clock
        self.user = {}
        self.last = {"action": -1e9, "ask": -1e9}

    def wait_user(self, user, seconds):
        left = self.user.get(user, -1e9) + seconds - self.clock()
        return max(0.0, left)

    def wait_kind(self, kind, seconds):
        return max(0.0, self.last[kind] + seconds - self.clock())

    def mark(self, user, kind):
        now = self.clock()
        self.user[user] = now
        self.last[kind] = now
        if len(self.user) > 500:                                   # never grow without limit
            for name in sorted(self.user, key=self.user.get)[:250]:
                del self.user[name]


@dataclass
class Result:
    status: str               # "done", "answered", "ignored", "blocked", "cooldown", "refused", "off", "failed"
    kind: str = ""            # "ask" / "action" / ""
    user: str = ""
    text: str = ""
    note: str = ""


class ChatDirector:
    """Decides what happens to each chat message. The three `do_*` functions are the only things that touch the game or her voice."""

    def __init__(self, settings, state_provider, do_action, do_ask, say, clock, quiet_provider=None):
        self.settings = settings
        self.clock = clock
        self.quiet_provider = quiet_provider    # () -> True when she is not busy (None = never hold anything back)
        self.held = deque()                     # (time, user, question) waiting for a quiet moment
        self.state_provider = state_provider
        self.do_action = do_action      # (action) -> True when it was done
        self.do_ask = do_ask            # (user, question) -> True when she answered
        self.say = say                  # (key, fields) -> speaks one of her streaming lines
        self.cool = Cooldowns(clock)
        self.log = deque(maxlen=40)     # what happened lately, for the dashboard
        self.asked = {}                 # viewer -> how many of their questions she has answered this session (so she can say 'welcome back')

    def option(self, name, default=None):
        return self.settings.get("streaming." + name, default)

    def _number(self, name, default):
        try:
            return max(0.0, float(self.option(name, default)))
        except (TypeError, ValueError):
            return float(default)

    def handle(self, message, test=False):
        result = self._handle(message, test)
        if result.status != "ignored":
            self.log.append(result)
        return result

    def _handle(self, message, test=False):
        user = clean_name(message.user)
        if not self.option("enabled", False) and not test:
            return Result("ignored", user=user)
        parsed = parse(message.text, self.option("prefix", DEFAULT_PREFIX))
        if parsed is None:
            return Result("ignored", user=user)
        kind, what = parsed
        text = tidy(message.text)
        if not message.owner:
            who = str(self.option("who", "everyone"))
            if who == "mods" and not message.mod:
                return Result("blocked", kind, user, text, "moderators only")
            if who == "subscribers" and not (message.sub or message.mod):
                return Result("blocked", kind, user, text, "subscribers only")
        if re.search(r"https?://|www\.|\.com\b", what if kind == "ask" else ""):
            return Result("blocked", kind, user, text, "link")
        if kind == "ask":
            if not self.option("ask_enabled", True):
                return Result("blocked", kind, user, text, "questions are off")
            if len(what) > MAX_QUESTION:
                return Result("blocked", kind, user, text, "too long")
            if has_blocked_word(what, split_words(self.option("blocked_words", ""))):
                return Result("blocked", kind, user, text, "blocked word")
        else:
            action = BY_KEY[what]
            if not self.option("act_" + action.key, action.default_on):
                return Result("blocked", kind, user, text, "that action is off")
        # cooldowns (the streamer is not limited per viewer)
        if not message.owner and self.cool.wait_user(user, self._number("user_cooldown", 45)) > 0:
            return Result("cooldown", kind, user, text, "viewer cooldown")
        gap = "action_cooldown" if kind == "action" else "ask_cooldown"
        if self.cool.wait_kind(kind, self._number(gap, 20 if kind == "action" else 10)) > 0:
            return Result("cooldown", kind, user, text, "busy")
        if kind == "ask":
            if self._should_hold():
                limit = int(self._number("hold_max", 4))
                if len(self.held) >= limit:
                    return Result("blocked", kind, user, what, "too many waiting (%d)" % limit)
                self.cool.user[user] = self.cool.clock()           # the viewer's own cooldown starts now
                self.held.append((self.clock(), user, what))
                return Result("held", "ask", user, what, "waiting for a quiet moment (%d waiting)" % len(self.held))
            self.cool.mark(user, "ask")
            ok = self.do_ask(user, what)
            return Result("answered" if ok else "failed", "ask", user, what)
        reason = action_blocker(action, self.state_provider())
        if reason:
            self.say("StreamChat_Refused", {"user": user, "action": action.label, "reason": reason})
            return Result("refused", "action", user, action.label, reason)
        self.cool.mark(user, "action")
        self.say("StreamChat_Action", {"user": user, "action": action.label})
        ok = self.do_action(action)
        return Result("done" if ok else "failed", "action", user, action.label)

    # ---- held questions ----
    def _should_hold(self):
        """True when a question should wait: holding is on, she is busy, or others are already waiting (first come, first served)."""
        if self.quiet_provider is None or not self.option("hold", True):
            return False
        if self.held:
            return True
        try:
            return not self.quiet_provider()
        except Exception:
            return False

    def pump(self):
        """Called about once a second. When it is quiet, answers the OLDEST held question (one at a time).
        Questions that waited too long (hold_max_age seconds, default 5 minutes) are dropped: the moment has passed."""
        if not self.held:
            return None
        now = self.clock()
        max_age = self._number("hold_max_age", 300)
        while self.held and max_age and now - self.held[0][0] > max_age:
            _t, user, question = self.held.popleft()
            self.log.append(Result("blocked", "ask", user, question, "waited too long"))
        if not self.held:
            return None
        if not self.option("enabled", False):
            self.held.clear()                                    # chat was switched off: forget them
            return None
        if self.cool.wait_kind("ask", self._number("ask_cooldown", 10)) > 0:
            return None
        try:
            if self.quiet_provider is not None and not self.quiet_provider():
                return None
        except Exception:
            return None
        _t, user, question = self.held.popleft()
        self.cool.last["ask"] = self.clock()
        ok = self.do_ask(user, question)
        result = Result("answered" if ok else "failed", "ask", user, question, "was held")
        self.log.append(result)
        return result
