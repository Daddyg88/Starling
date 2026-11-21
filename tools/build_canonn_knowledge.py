"""Turn a clone of the Canonn archive (https://github.com/canonn-science/canonn.science) into config/knowledge/canonn.json.

Usage (needs only Python):
    git clone --depth 1 https://github.com/canonn-science/canonn.science canonn
    python tools/build_canonn_knowledge.py canonn [--check]

For each article (a folder with article.json and body.html) it keeps the title, the category and a SHORT plain-text opening (two or three
sentences, 340 characters at most), so she can answer "what is a bullet mollusc" or "tell me about Crowther's Rest" and say where it is from.
It does NOT copy whole articles. Skipped: the Merchandise category, Obsolete/Incomplete articles, policy, test and merchandise pages,
and the event and faction-mission announcements (out of date the day after). The author field is not kept (a few articles name their authors in their own opening).
--check only prints what it would write.
"""

import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "config" / "knowledge" / "canonn.json"
sys.path.insert(0, str(ROOT))

SKIP_CATEGORIES = {"Merchandise", "Obsolete/Incomplete"}
SKIP_SECTIONS = {"event", "faction-bgs", "uncategorised"}
SKIP_TITLES = ("merchandise", "privacy policy", "discord", "guidelines", "formatting test", "html test", "test page")
SKIP_SLUGS = {"0html-test"}
MAX_CHARS = 340
MIN_CHARS = 90
BOILERPLATE = ("jquery(function", "typed(", "function(", "var ", "window.", "document.", "loading...", "click here to")
# words that say nothing about WHICH article is meant: a title made only of these is never used as a key
GENERIC = {"lore", "news", "guide", "about", "list", "story", "report", "update", "weekly", "page", "media", "part", "edition", "week", "summary",
           "article", "bugle", "canonn", "the", "and", "of", "in", "to", "for", "a", "an", "on", "at", "by", "with", "from", "is", "are", "what", "how",
           "why", "game", "site", "base", "ship", "ships", "system", "systems", "planet", "planets", "star", "stars", "data", "log", "logs", "notes", "info"}
CATEGORY_SAYING = {"Cartographics & Exploration": "exploration", "Biology & Geology": "biology and geology", "Xenology": "xenology",
                   "Civilisation": "civilisation", "Technology": "technology", "Bureau of Governance & Settlement": "governance and settlement",
                   "News and Events": "the news", "About Canonn": "about Canonn", "Useful Links": "useful links"}


class _Text(HTMLParser):
    SKIP = {"script", "style", "figure", "iframe", "table", "noscript", "svg", "figcaption", "nav", "form", "button"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.depth = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1
        elif tag in ("p", "br", "li", "div", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1
        elif tag in ("p", "li", "div", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.depth:
            self.parts.append(data)


def plain(text):
    parser = _Text()
    try:
        parser.feed(text)
    except Exception:
        return ""
    return html.unescape("".join(parser.parts))


def speakable(text):
    """Text for her voice: no web addresses, brackets or stray symbols."""
    text = re.sub(r"https?://\S+|www\.\S+", "", text)
    text = re.sub(r"\s*,?\s*(?:at |latitude )?-?\d{1,3}\.\d{2,},\s*-?\d{1,3}\.\d{2,}", "", text)          # coordinates are no good read aloud: the link has them
    text = re.sub(r"\[[^\]]*\]|\([^)]*\)", "", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = text.replace("–", "-").replace("—", "-").replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    text = text.replace("&", " and ").replace("#", " number ")
    text = re.sub(r"[*_~^|<>{}\\]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def opening(body):
    """The first two or three sentences (340 characters at most) of the first real paragraphs; '' when there is nothing to say."""
    paragraphs = [speakable(p) for p in plain(body).split("\n")]
    paragraphs = [p for p in paragraphs if len(p) >= 40 and not any(b in p.lower() for b in BOILERPLATE)]
    if not paragraphs:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(paragraphs[:3]))
    out = ""
    for sentence in sentences:
        if len(out) + len(sentence) + 1 > MAX_CHARS and out:
            break
        if len(sentence) > MAX_CHARS and not out:
            cut = sentence[:MAX_CHARS].rsplit(" ", 1)[0].rstrip(",;:- ")
            return cut + "."
        out = (out + " " + sentence).strip()
        if len(out) >= 170:
            break
    return out


def key_words(title):
    """The words the question must contain: the title without the little words ('The Guardian Ruins' -> guardian ruins)."""
    from personality.knowledge import words_of
    words = [w for w in words_of(re.sub(r"[^A-Za-z0-9' ]+", " ", title)) if w not in GENERIC]
    return words[:6]


LEAD_WORDS = {"study", "report", "analysis", "investigation", "guide", "research", "overview", "introduction"}
TOO_COMMON = {"exploration", "mining", "trading", "combat", "engineering", "tutorial", "introduction", "basics", "faq", "tips", "events", "community", "science",
              "tools", "resources", "history", "research", "mystery", "mysteries", "explorer", "explorers", "pilot", "pilots", "overview", "welcome", "hello", "start"}
EXTRA_KEYS = {"about-us": [["canonn"], ["canonn", "research", "group"], ["canonn", "interstellar"]]}


def keys_for(title, slug=""):
    from personality.knowledge import words_of
    words = key_words(title)
    if len(words) <= 1 and (not words or len(words[0]) < 5 or words[0].isdigit()):
        everything = [w for w in words_of(re.sub(r"[^A-Za-z0-9' ]+", " ", title)) if w not in ("the", "a", "an", "of", "and")]
        words = everything[:6] if len(everything) >= 2 else []          # 'Site 94' keeps its 'site'; a lone 'Tau' would catch too much
    if not words or (len(words) == 1 and words[0] in TOO_COMMON):
        return []                                       # a section index called 'Exploration' must not answer "what is exploration"
    keys = [words]
    short = [w for w in words if w not in LEAD_WORDS]
    if short != words and short and (len(short) >= 2 or len(short[0]) >= 5):
        keys.append(short)                              # 'A Study on the Brain Trees' is also found by 'brain trees'
    return keys + EXTRA_KEYS.get(slug, [])


def load_articles(folder):
    found = []
    for path in sorted(folder.glob("*/article.json")):
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        slug = path.parent.name
        if slug in SKIP_SLUGS or meta.get("section") in SKIP_SECTIONS:
            continue
        title = str(meta.get("title") or "").strip()
        if not title or any(s in title.lower() for s in SKIP_TITLES):
            continue
        cats = [c.get("category") if isinstance(c, dict) else c for c in (meta.get("categories") or [])]
        if any(c in SKIP_CATEGORIES for c in cats):
            continue
        body = next(iter(sorted(path.parent.glob("body.*"))), None)
        if body is None:
            continue
        text = opening(body.read_text(encoding="utf-8", errors="replace"))
        if len(text) < MIN_CHARS or "==+" in text or text.startswith("="):
            continue
        found.append({"title": speakable(title), "slug": slug, "section": meta.get("section") or "", "cats": [c for c in cats if c], "text": text})
    return found


def build(folder):
    articles = load_articles(folder)
    order = {"codex": 0, "pages": 1, "resources": 2, "lab69xia": 3, "media": 4, "news": 5}
    articles.sort(key=lambda a: (order.get(a["section"], 9), a["title"].lower()))          # on a tie the first one wins: the codex first
    entries, seen = [], set()
    for a in articles:
        keys = keys_for(a["title"], a["slug"])
        marker = tuple(keys[0]) if keys else None
        if not keys or marker in seen:
            continue
        seen.add(marker)
        where = next((CATEGORY_SAYING.get(c) for c in a["cats"] if c in CATEGORY_SAYING), "")
        ending = " That is from the Canonn research archive%s." % ((", under " + where) if where else "")
        entries.append({"k": keys, "a": a["text"].rstrip() + ending,
                        "src": "https://science.canonn.tech/%s/%s" % (a["section"], a["slug"])})
    return entries, len(articles)


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    folder = Path(args[0]) / "content" / "articles"
    if not folder.is_dir():
        print("No content/articles folder in", args[0])
        return 2
    entries, total = build(folder)
    print("%d articles with a usable opening, %d with a usable key, about %d KB" % (total, len(entries), len(json.dumps(entries)) // 1024))
    if "--check" in argv:
        for e in entries[:8]:
            print(e["k"], "->", e["a"][:110])
        return 0
    OUT.write_text(json.dumps({
        "_help": "Short openings of articles from the Canonn Interstellar Research Group archive (https://science.canonn.tech), made by tools/build_canonn_knowledge.py. "
                 "Credit: Canonn Interstellar Research Group and the authors of the articles. Only the first few sentences are kept; the src field says where the full article is.",
        "entries": entries}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
