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
import html
import json
import math
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
FANDOM = "https://elite-dangerous.fandom.com"          # the Elite Dangerous wiki: used for questions about Elite ships
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


_NUMBER_NAMES = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "i": "1", "ii": "2", "iii": "3", "iv": "4",
                 "v": "5", "vi": "6"}


def norm_ship(text):
    """'Cobra Mk III', 'cobra mark three' and 'Cobra Mark 3' all become 'cobra mark 3'; 'Fer-de-Lance' becomes 'fer de lance'."""
    text = re.sub(r"['\u2019]", "", (text or "").lower())
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\bmk\s*(?=[a-z0-9])", "mark ", text)
    text = re.sub(r"\bmark\s*(one|two|three|four|five|six|vi|iv|v|iii|ii|i|[1-6])\b", lambda m: "mark " + _NUMBER_NAMES.get(m.group(1), m.group(1)), text)
    return re.sub(r"\s+", " ", text).strip()


def ship_in(tidy, names):
    """The display name of the Elite ship a sentence is about ('Anaconda', 'Cobra Mark 3'), longest name first, or None."""
    padded = " %s " % norm_ship(tidy)
    for name in sorted(set(names), key=len, reverse=True):
        if (" %s " % norm_ship(name)) in padded:
            return name
    return None


def first_paragraph(page_html):
    """The first real paragraph of a wiki page's HTML (the boxes, tables and scripts around it are skipped), as plain text."""
    text = re.sub(r"(?is)<(script|style|aside|table|figure|sup)\b.*?</\1>", " ", page_html or "")
    for paragraph in re.findall(r"(?is)<p\b[^>]*>(.*?)</p>", text):
        plain = html.unescape(re.sub(r"(?s)<[^>]+>", "", paragraph))
        plain = re.sub(r"\s+", " ", plain).strip()
        if len(plain) >= 60:
            return plain
    return None


def covers(wanted, title, extract):
    """Does the page really talk about the subject? 'green gas giant' must not be answered with 'Giant squid':
    at least 60 percent of the subject's words have to be in the title or the start of the article."""
    wanted = {w for w in wanted if len(w) > 1}
    if not wanted:
        return True
    have = set(words_of("%s %s" % (title, (extract or "")[:500])))
    return len(wanted & have) >= math.ceil(0.6 * len(wanted))


def default_fetch(url):
    """GET a Wikipedia (or Elite Dangerous wiki) JSON address. Only those two sites, short timeout, small answers, None on any problem."""
    if not (url.startswith(HOST + "/") or url.startswith(FANDOM + "/")):
        return None
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            return None
        return json.loads(data.decode("utf-8"))
    except Exception as exc:
        log.info("Lookup could not fetch %s: %s", url.split("?")[0], exc)
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
    def __init__(self, settings, learned, fetch=default_fetch, clock=time.monotonic, background=True, ships=None):
        self.ships = ships                    # a function giving the ship names she knows (core/ships.py), or None
        self.settings = settings
        self.learned = learned
        self.fetch = fetch
        self.clock = clock
        self.background = background
        self._last = -1e9
        self._failed = {}                     # key -> time

    def enabled(self):
        return bool(self.settings.get("brain.lookup", False))

    QUESTION_START = re.compile(r"^(?:what|how|tell me|explain|describe|is|does|can|which|who|why|do)\b")

    def ship_subject(self, tidy):
        """('ship', 'Anaconda') when the question is about an Elite ship, else None. Ships come from the Elite Dangerous wiki."""
        if self.ships is None or not self.QUESTION_START.match(tidy):
            return None
        words = tidy.split()
        if len(words) > 14 or any(w in BLOCKED for w in words) or freechat.is_crisis(tidy):
            return None
        name = ship_in(tidy, self.ships())
        return ("ship", name) if name else None

    def known(self, tidy):
        """A fact saved earlier: (title, text) or None. Works offline."""
        found = self.ship_subject(tidy) or subject_of(tidy)
        if not found or found[0] not in ("def", "ship"):
            return None
        item = self.learned.get(self.key(*found))
        return (item.get("title", ""), item["text"]) if item else None

    def should_try(self, tidy):
        """(kind, subject) if a live lookup is allowed right now, else None."""
        if not self.enabled():
            return None
        found = self.ship_subject(tidy) or subject_of(tidy)
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
        result = self._search_ship(subject) if kind == "ship" else self._search(subject)
        if result is None or result == "offline":
            self._failed[key] = self.clock() if result is None else self.clock() - RETRY_AFTER_FAIL + 60
            return result
        if kind in ("def", "ship"):
            self.learned.add(key, result[0], result[1])
        return result

    @staticmethod
    def key(kind, subject):
        if kind == "ship":
            return "ship:%s" % norm_ship(subject)
        return "%s:%s" % (kind, " ".join(words_of(subject)))

    def _search_ship(self, name):
        """(title, text) from the Elite Dangerous wiki, or None / 'offline'. The page title must start with the ship's first word."""
        query = urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": name, "srlimit": 4, "format": "json", "srnamespace": 0})
        data = self.fetch("%s/api.php?%s" % (FANDOM, query))
        if data is None:
            log.info("Elite wiki: could not reach %s (no answer to the search for %r)", FANDOM, name)
            return "offline"
        try:
            hits = data["query"]["search"]
        except (TypeError, KeyError):
            log.info("Elite wiki: the search for %r came back in a shape I did not expect: %.200s", name, str(data))
            return None
        titles = [str(hit.get("title", "")) for hit in hits]
        log.info("Elite wiki: search for %r found %s", name, titles)
        first = norm_ship(name).split()[0]
        for title in titles:
            if not norm_ship(title).startswith(first) or ":" in title:
                continue
            extract = self._wiki_intro(title)
            if not extract:
                log.info("Elite wiki: found the page %r but could not read its first paragraph", title)
                continue
            text = tidy_extract(extract)
            if text:
                return title, text
            log.info("Elite wiki: the first paragraph of %r was not usable: %.120s", title, extract)
        return None

    def _wiki_intro(self, title):
        """The first paragraph of a wiki page: the plain-text extract, or the short abstract if the wiki does not offer extracts."""
        query = urllib.parse.urlencode({"action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1, "redirects": 1, "format": "json",
                                        "titles": title})
        page = self.fetch("%s/api.php?%s" % (FANDOM, query))
        try:
            for item in (page["query"]["pages"] or {}).values():
                if item.get("extract"):
                    return item["extract"]
        except (TypeError, KeyError, AttributeError):
            pass
        query = urllib.parse.urlencode({"titles": title, "abstract": 400})
        page = self.fetch("%s/api/v1/Articles/Details?%s" % (FANDOM, query))
        try:
            for item in (page["items"] or {}).values():
                if item.get("abstract"):
                    return item["abstract"]
        except (TypeError, KeyError, AttributeError):
            pass
        query = urllib.parse.urlencode({"action": "parse", "page": title, "prop": "text", "section": 0, "redirects": 1, "format": "json",
                                        "disableeditsection": 1})
        page = self.fetch("%s/api.php?%s" % (FANDOM, query))
        try:
            return first_paragraph(page["parse"]["text"]["*"])
        except (TypeError, KeyError, AttributeError):
            return None

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
            if not covers(wanted, title, extract):
                continue
            text = tidy_extract(extract)
            if text:
                return page.get("title") or title, text
        return None

    def handle_forget(self, tidy):
        if FORGET.search(tidy):
            return self.learned.clear()
        return None
