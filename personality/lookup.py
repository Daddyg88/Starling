"""
LOOKING THINGS UP - when she does not know, she can ask Wikipedia, say what it says, and remember it.

OFF by default (Personality page: "She can look things up online"). When it is on, and she is asked a what/who/where/how-style
question she has no answer for, she:
  1. says "let me look that up",
  2. sends ONLY the topic words (for example "quasar") to the English Wikipedia search, never your whole sentence, your name
     or anything about your game,
  3. reads the first sentence or two of the best matching article, cleans it (no web links, bad words or odd symbols),
  4. says it, with "according to Wikipedia" so nobody mistakes it for something she worked out,
  5. for "what is / who is" questions, saves it in data/learned_facts.json so next time she answers instantly and offline.

Safe by design: no match = she says she could not find anything reliable (never a guess); pages that are lists or
"may refer to" pages are ignored; questions with personal words (I, my, you...), worrying words, or too many words are never
sent; at most one lookup every 8 seconds; failed topics are not retried for 10 minutes. "Forget what you looked up" deletes
the saved facts. data/ is private to your PC. The saved facts are plain public text, so you can send the file to be added
to everyone's config/knowledge.
"""
import json
import os
import re
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from datetime import date

from core.logger import get_logger
from personality import freechat
from personality.knowledge import words_of
from personality.llm import clean_reply

log = get_logger("lookup")

HOST = "https://en.wikipedia.org"
USER_AGENT = "Starling/0.68 (Elite Dangerous ship companion; https://github.com/Daddyg88/Starling)"
TIMEOUT = 4
MAX_BYTES = 300_000
MIN_GAP_SECONDS = 8
RETRY_AFTER_FAIL = 600
MAX_SUBJECT_WORDS = 6
MAX_LEARNED = 400
PERSONAL = {"i", "im", "ive", "my", "me", "mine", "myself", "you", "your", "yours", "youre", "we", "our", "us", "starling", "commander",
            "cmdr"}
BLOCKED = {"sex", "sexual", "porn", "nude", "naked", "kill", "suicide", "murder", "rape", "drug", "drugs", "cocaine", "heroin", "bomb",
           "weapon", "terror", "nazi", "racist", "fuck", "shit", "cunt", "penis", "vagina", "boob", "boobs", "anal", "dick", "cock", "tits"}
DEFINE = re.compile(r"^(?:what|who)(?: is| are| was| were|s) (?:a |an |the )?(?P<s>.+)$|^(?:tell me about|explain|describe|define|what do you know about) (?:a |an |the )?(?P<t>.+)$")
DETAIL = re.compile(r"^(?:where|when)(?: is| was| are| were| did| does|s)? (?:a |an |the )?(?P<s>.+)$|"
                    r"^how (?:tall|big|old|far|long|many|much|fast|heavy|deep|wide|high|hot|cold|large|small) (?:is|are|was|were|did|does|do) (?:a |an |the )?(?P<d>.+)$|"
                    r"^who (?:invented|discovered|wrote|painted|made|created|founded|built|designed|directed|composed|sang) (?:a |an |the )?(?P<w>.+)$")
STRIP_SUBJECT = re.compile(r"^(?:the )?(?:meaning of |definition of )?|\b(?:called|about|exactly|actually|really|again|please)$")
FORGET = re.compile(r"\b(?:forget|clear|delete|wipe)\b.*\b(?:looked up|learned from|learnt from|learned facts|learnt facts|wikipedia|internet facts)\b")


class LearnedFacts:
    """data/learned_facts.json: {"def:quasar": {"title": "Quasar", "text": "...", "on": "2026-10-27"}}"""

    def __init__(self, path):
        self.path = path
        self.items = {}
        self._lock = threading.Lock()
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                self.items = {str(k): v for k, v in data.items() if isinstance(v, dict) and v.get("text")}
        except FileNotFoundError:
            pass
        except Exception:
            log.warning("Could not read %s; starting with no learned facts", path)

    def get(self, key):
        return self.items.get(key)

    def add(self, key, title, text):
        with self._lock:
            self.items[key] = {"title": title, "text": text, "on": date.today().isoformat()}
            while len(self.items) > MAX_LEARNED:
                self.items.pop(next(iter(self.items)))
            self._save()

    def clear(self):
        with self._lock:
            count = len(self.items)
            self.items = {}
            try:
                os.remove(self.path)
            except OSError:
                pass
            return count

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle, temp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                json.dump(self.items, out, indent=1, ensure_ascii=False)
            os.replace(temp, self.path)
        except OSError:
            log.exception("Could not save the learned facts")


def subject_of(tidy):
    """('def' or 'detail', 'quasar') for a lookup-able question, or None. Personal or worrying questions are never lookup-able."""
    match = DEFINE.match(tidy)
    kind = "def"
    subject = None
    if match:
        subject = match.group("s") or match.group("t")
    else:
        match = DETAIL.match(tidy)
        if match:
            kind = "detail"
            subject = match.group("s") or match.group("d") or match.group("w")
    if not subject:
        return None
    subject = re.sub(r"\b(?:called|please|exactly|actually|then|again)\b", " ", subject)
    subject = re.sub(r"^(?:the |a |an )+", "", re.sub(r"\s+", " ", subject).strip())
    words = subject.split()
    if not words or len(words) > MAX_SUBJECT_WORDS:
        return None
    if any(w in PERSONAL or w in BLOCKED for w in words) or any(w in BLOCKED for w in tidy.split()):
        return None
    if sum(c.isdigit() for c in subject) > 4 or freechat.is_crisis(tidy):
        return None
    if kind == "def" and words[0] in ("it", "that", "this", "there", "he", "she", "they", "happening", "wrong", "going", "next", "good", "up"):
        return None
    return kind, subject


def default_fetch(url):
    """GET a Wikipedia JSON address. Only https://en.wikipedia.org, short timeout, small answers, None on any problem."""
    if not url.startswith(HOST + "/"):
        return None
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            return None
        return json.loads(data.decode("utf-8"))
    except Exception as exc:
        log.info("Lookup could not reach Wikipedia: %s", exc)
        return None


def _without_brackets(text):
    """Takes out (brackets) and [notes], including brackets inside brackets: 'Tritium (from Greek (trítos) third) is...' -> 'Tritium is...'"""
    text = text or ""
    for _ in range(6):
        shorter = re.sub(r"\([^()]*\)|\[[^\[\]]*\]", "", text)
        if shorter == text:
            break
        text = shorter
    return re.sub(r"[()\[\]]", "", text)


def tidy_extract(text):
    """The start of a Wikipedia summary, ready to say aloud: brackets out, one or two sentences (at most about 220 letters), safe words only.
    The cut comes first so a long paragraph full of numbers is not thrown away because of the ones she will never say."""
    text = _without_brackets(text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", re.sub(r"\s+", " ", text)).strip()
    sentences = [part for part in re.split(r"(?<=[.!?])\s+", text) if part]
    if sentences:
        text = sentences[0]
        if len(text) < 60 and len(sentences) > 1 and len(text) + len(sentences[1]) < 220:
            text += " " + sentences[1]
    return clean_reply(text, allow_mature=False)


class OnlineLookup:
    def __init__(self, settings, learned, fetch=default_fetch, clock=time.monotonic, background=True):
        self.settings = settings
        self.learned = learned
        self.fetch = fetch
        self.clock = clock
        self.background = background
        self._last = -1e9
        self._failed = {}                     # key -> time

    def enabled(self):
        return bool(self.settings.get("brain.lookup", False))

    @staticmethod
    def key(kind, subject):
        return "%s:%s" % (kind, " ".join(words_of(subject)))

    def known(self, tidy):
        """A fact saved earlier: (title, text) or None. Works offline."""
        found = subject_of(tidy)
        if not found or found[0] != "def":
            return None
        item = self.learned.get(self.key(*found))
        return (item.get("title", ""), item["text"]) if item else None

    def should_try(self, tidy):
        """(kind, subject) if a live lookup is allowed right now, else None."""
        if not self.enabled():
            return None
        found = subject_of(tidy)
        if not found:
            return None
        now = self.clock()
        if now - self._last < MIN_GAP_SECONDS:
            return None
        if now - self._failed.get(self.key(*found), -1e9) < RETRY_AFTER_FAIL:
            return None
        return found

    def find(self, kind, subject):
        """(title, text) from Wikipedia, or None. Marks the topic failed when nothing reliable turns up."""
        self._last = self.clock()
        key = self.key(kind, subject)
        result = self._search(subject)
        if result is None or result == "offline":
            self._failed[key] = self.clock() if result is None else self.clock() - RETRY_AFTER_FAIL + 60
            return result
        if kind == "def":
            self.learned.add(key, result[0], result[1])
        return result

    def _search(self, subject):
        query = urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": subject, "srlimit": 3, "format": "json",
                                        "srnamespace": 0})
        data = self.fetch("%s/w/api.php?%s" % (HOST, query))
        if data is None:
            return "offline"
        try:
            hits = data["query"]["search"]
        except (TypeError, KeyError):
            return None
        wanted = set(words_of(subject))
        for hit in hits:
            title = str(hit.get("title", ""))
            have = set(words_of(title))
            if not have or not (wanted & have) or len(wanted & have) < max(1, len(wanted) // 2):
                continue
            if title.lower().startswith(("list of", "outline of", "index of")):
                continue
            page = self.fetch("%s/api/rest_v1/page/summary/%s" % (HOST, urllib.parse.quote(title.replace(" ", "_"), safe="")))
            if not isinstance(page, dict) or page.get("type") not in ("standard", None):
                continue
            extract = page.get("extract") or ""
            if not extract or "may refer to" in extract[:200] or "disambiguation" in str(page.get("description", "")).lower():
                continue
            text = tidy_extract(extract)
            if text:
                return page.get("title") or title, text
        return None

    def handle_forget(self, tidy):
        if FORGET.search(tidy):
            return self.learned.clear()
        return None
