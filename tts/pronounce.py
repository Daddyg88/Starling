"""HOW SHE SAYS NUMBERS AND HARD WORDS (0.96.4). Applied to the text just before a voice reads it (tts/kokoro_tts.py); what is shown or logged is untouched.

1. Decimals: "7.9" becomes "7 point 9" and "28.4 million" becomes "28 point 4 million", so the point is never dropped ("seven nine"). The digits after the
   point are said one by one ("3.14" = "three point one four"). Left alone: IDs like 21.02.002, version numbers like 0.96.3, and a full stop at the end of a sentence.
2. Units: "500 m" -> "500 metres", "2 km" -> "2 kilometres", "1.2 g" -> "1 point 2 gee" (a lone letter is read as a letter otherwise).
3. (0.96.51) Years are said as years ("in 1994" = "nineteen ninety-four", Elite's "in 3125" = "thirty-one twenty-five"), dates as ordinals ("16th" =
   "sixteenth"), and Elite system codes letter by letter ("NL-N C23-4" = "N L dash N, C 2 3 dash 4"). Acronyms such as SRV and DSSA are in the word list below.
4. Hard words: config/pronunciations.json lists Latin and game words (Fonticulua, Tectonicas, terraformable...) with a respelling the voice reads correctly,
   plus extra changes for the Australian voice only (metres). Edit that file to fix a word; an empty list switches it off.
"""
import json
import re

from core import paths
from core.logger import get_logger

log = get_logger("pronounce")

_DECIMAL = re.compile(r"(?<![\d.,])(\d+)\.(\d+)(?!\d|\.\d)")
_METRES = re.compile(r"(?<=\d)\s?m\b(?!\.\d)")
_KM = re.compile(r"(?<=\d)\s?km\b")
_GEE = re.compile(r"(?<=\d)\s?g\b(?!\w)")

_YEAR = re.compile(r"(?<![\d.,$#/-])\b(?:(?<=in )|(?<=of )|(?<=by )|(?<=since )|(?<=until )|(?<=from )|(?<=and )|(?<=during )|(?<=before )|(?<=after )"
                   r"|(?<=January )|(?<=February )|(?<=March )|(?<=April )|(?<=May )|(?<=June )|(?<=July )|(?<=August )|(?<=September )"
                   r"|(?<=October )|(?<=November )|(?<=December ))([1-3]\d{3})\b(?![\d,.]\d)(?!\s(?:credits?|tonnes?|tons?|metres?|kilometres?|light|ly|units?|cr|jumps?|percent|%))")
_ORDINAL = re.compile(r"\b([1-9]|[12]\d|3[01])(st|nd|rd|th)\b")
_SYSTEM_CODE = re.compile(r"\b([A-Z]{2})-([A-Z]) ([A-Ha-h])(\d{1,2})(?:-(\d{1,4}))?\b")
_SALUTE = re.compile(r"(?<![A-Za-z0-9])[Oo]7(?![A-Za-z0-9])")      # the Elite salute o7: say "oh seven", not "o, 7"
_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen").split()
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_ORDINAL_WORDS = {1: "first", 2: "second", 3: "third", 5: "fifth", 8: "eighth", 9: "ninth", 12: "twelfth", 20: "twentieth", 30: "thirtieth"}

# "live" is two words (0.96.127): the verb "liv" (I live in London) and the adjective "lyve" (live music, going live). Decided from the word before and after.
_LIVE = re.compile(r"\b(?:(\w+['’]?\w*)\s+)?(live|Live)(s)?\b(?:\s+(\w+))?")
_LIVE_ADJ_BEFORE = {"go", "goes", "going", "gone", "went", "be", "being", "been", "is", "are", "was", "were", "am", "a", "an", "the", "this", "that", "our", "my", "your", "his",
                    "her", "its", "their", "on", "not", "so", "very", "really", "truly", "now", "stream", "streams", "streaming", "streamed", "broadcast", "broadcasting",
                    "play", "plays", "playing", "played", "with", "some", "any", "no", "and", "for", "of", "or", "to_go"}
_LIVE_VERB_BEFORE = {"i", "you", "we", "they", "who", "to", "will", "would", "can", "could", "must", "shall", "should", "might", "may", "do", "dont", "don't", "does", "doesn't",
                     "did", "still", "also", "only", "ever", "always", "never", "just", "where", "there", "people", "i'll", "i'd", "you'll", "you'd", "we'll", "we'd", "they'll",
                     "how", "wish", "want", "wants", "wanted", "hope", "love", "loves", "like", "likes", "let", "let's", "lets", "where", "whoever"}
_LIVE_NOUN_AFTER = {"stream", "streams", "streaming", "broadcast", "broadcasts", "music", "show", "shows", "wire", "feed", "feeds", "event", "events", "audience", "chat",
                    "ammo", "ammunition", "round", "rounds", "fire", "signal", "update", "updates", "action", "performance", "session", "demo", "video", "coverage",
                    "data", "map", "band", "gig", "concert", "TV", "radio", "recording", "commentary", "reaction", "reactions", "subs", "sub", "cargo", "animal",
                    "animals", "bait", "creature", "creatures", "wild"}
_LIFE_PLURAL_BEFORE = {"nine", "many", "their", "your", "our", "my", "two", "three", "four", "five", "several", "few", "more", "less", "countless", "save", "saved", "saving",
                       "lose", "lost", "losing", "take", "taken", "taking", "of", "innocent", "human", "whose", "all", "other", "past", "new", "second", "third", "his", "her", "its"}

# Other English words spelt one way and said two ways (0.96.129). Only the cases that really occur in her speech, decided from the words around
# them, and respelt with a word (or spelling) every voice reads one way: read (past) = red, lead (the metal) = led, close (verb) = cloze,
# close (near) = cloce, row = roe, bass = base, tear (rip) = tare, tear-shaped = teer-shaped, desert = dez-ert, content (happy) = kun-tent,
# no use = no yoos, used to = yoost to, buffet = buh-fay, record (verb) = ri-cord. Anything unclear is left to the voice.
_WORD = re.compile(r"[A-Za-z'’]+")
_ADJ_CLOSE_BEFORE = {"stay", "stays", "stayed", "staying", "too", "so", "very", "quite", "bit", "up", "it's", "that's", "get", "got", "getting", "keep", "kept", "are", "is",
                     "was", "were", "be", "being", "been", "really", "pretty", "how", "come", "comes", "came", "coming", "a", "an", "any", "no", "its", "my", "your", "our",
                     "their", "his", "her", "this", "that", "stand", "stood", "hold", "held", "look", "looks", "looked", "looking", "feel", "feels", "felt", "fly", "flew",
                     "flying", "sit", "sat", "sitting", "walk", "stick", "stuck", "sticking"}
_ADJ_CLOSE_AFTER = {"to", "by", "call", "calls", "one", "ones", "eye", "friends", "friend", "enough", "together", "quarters", "range", "shave", "encounter", "with",
                    "relationship", "ally", "allies", "second", "match", "race", "fight", "contact", "combat", "up", "behind", "ahead", "now", "again", "enough"}
_VERB_CLOSE_BEFORE = {"to", "will", "can", "could", "shall", "should", "would", "may", "might", "must", "please", "don't", "do", "didn't", "won't", "can't", "cannot",
                      "and", "or", "then", "never", "gonna", "let", "lets", "let's", "who", "you", "we", "they", "i", "i'll", "you'll", "we'll", "they'll", "i'd", "you'd"}
_VERB_CLOSE_AFTER = {"the", "it", "them", "this", "that", "my", "your", "a", "all", "our", "these", "those", "him", "her", "us", "down", "off", "out"}
_VERB_RECORD_BEFORE = {"to", "will", "can", "could", "shall", "should", "would", "may", "might", "must", "please", "don't", "do", "didn't", "won't", "can't", "cannot",
                       "gonna", "let", "let's", "i'll", "you'll", "we'll", "they'll", "who"}
_CONTENT_HAPPY_BEFORE = {"are", "am", "be", "feel", "feels", "felt", "quite", "very", "perfectly", "really", "so", "stay", "stays", "they're", "you're", "i'm", "we're",
                         "looking", "looks", "look", "seems", "seem", "seemed", "not", "reasonably", "fairly", "pretty", "rather", "just"}
_METAL_LEAD_BEFORE = {"melt", "melts", "melted", "of", "pure", "toxic", "heavy", "with", "and", "molten", "solid", "lump", "bars", "bar", "sheet", "sheets", "poisoning", "paint"}
_YOOST_BEFORE = {"i", "you", "we", "they", "he", "she", "it", "who", "and", "get", "gets", "getting", "got", "gotten", "am", "i'm", "you're", "we're", "they're", "he's",
                 "she's", "never", "not", "always", "still", "quite", "very", "so", "once", "just", "both", "also", "that", "there", "which", "what"}
_WORDS_OF_INTEREST = re.compile(r"\b(read|lead|close|record|content|row|rows|bass|tear|desert|deserts|use|used|buffet)\b|\b(?:tear)[- ]?(?:shaped|drop)", re.I)


def _near(text, start, end):
    """(the word before, the word after) inside the same sentence, lower case, '' when there is none."""
    before = text[:start]
    cut = max(before.rfind(". "), before.rfind("! "), before.rfind("? "), before.rfind("\n"), before.rfind(": "), before.rfind("; "), before.rfind(", "))
    previous = _WORD.findall(before[cut + 1:] if cut >= 0 else before)
    after = text[end:]
    upcoming = _WORD.search(after) if not re.match(r"\s*[.!?]", after) else None
    return (previous[-1].lower().replace("’", "'") if previous else ""), (upcoming.group(0).lower() if upcoming else ""), bool(previous)


def _case(source, new):
    if len(source) > 1 and source.isupper():
        return new.upper()
    return new[:1].upper() + new[1:] if source[:1].isupper() else new


def _say_heteronyms(text):
    """The words in the list above, respelt where the sentence makes the meaning clear."""
    if not _WORDS_OF_INTEREST.search(text):
        return text
    out = text
    # read, past tense: "I once read that...", "I've read", "had read", "I read this once"
    out = re.sub(r"(?<=\bonce )read\b|(?<=\bhad )read\b|(?<=\bhave )read\b|(?<=\bhas )read\b|(?<=\balready )read\b|(?<=['’]ve )read\b|(?<=['’]d )read\b"
                 r"|(?<=\bhave you )read\b|(?<=\bhad you )read\b", lambda m: "red", out, flags=re.I)
    out = re.sub(r"\b(I read)\b(?= (?:this|that|it|about|somewhere|a|an|the)\b[^.!?]{0,25}\b(?:once|somewhere|yesterday|earlier|before|ages ago|last (?:week|night|year))\b)",
                 lambda m: "I red", out)
    out = re.sub(r"\bI read (this|that) once\b", lambda m: "I red %s once" % m.group(1), out)

    def lead(m):
        before, after, _ = _near(m.string, m.start(), m.end())
        if before == "flight" and m.group(0)[0].isupper():
            return _case(m.group(0), "leed")
        if before in _METAL_LEAD_BEFORE:
            return _case(m.group(0), "led")
        return m.group(0)
    out = re.sub(r"\blead\b", lead, out, flags=re.I)

    def close(m):
        before, after, has_before = _near(m.string, m.start(), m.end())
        if before in _ADJ_CLOSE_BEFORE:
            return _case(m.group(0), "cloce")
        if before in _VERB_CLOSE_BEFORE and after not in _ADJ_CLOSE_AFTER:
            return _case(m.group(0), "cloze")
        if not has_before and after in _VERB_CLOSE_AFTER:
            return _case(m.group(0), "cloze")                  # "Close the map."
        if after in _ADJ_CLOSE_AFTER and after not in ("up", "now", "again"):
            return _case(m.group(0), "cloce")
        if after in ("now", "again") and before in ("get", "getting", "got", "coming", "come", "so"):
            return _case(m.group(0), "cloce")
        return m.group(0)
    out = re.sub(r"\bclose\b", close, out, flags=re.I)

    out = re.sub(r"\brow\b", lambda m: _case(m.group(0), "roe"), out, flags=re.I)
    out = re.sub(r"\brows\b", lambda m: _case(m.group(0), "roes"), out, flags=re.I)
    out = re.sub(r"\bbass\b", lambda m: _case(m.group(0), "base"), out, flags=re.I)
    out = re.sub(r"\btear[- ]?(shaped|drop)", lambda m: "teer-" + m.group(1), out, flags=re.I)
    out = re.sub(r"\b(tear)(?= (?:it|them|him|her|us|you|me|a|the|something|this|that|these|those|down|off|apart|away)\b)", lambda m: _case(m.group(1), "tare"), out, flags=re.I)
    out = re.sub(r"\b(desert)(s?)\b", lambda m: _case(m.group(1), "dez-ert") + m.group(2), out, flags=re.I)
    out = re.sub(r"\bbuffet\b", lambda m: _case(m.group(0), "buh-fay"), out, flags=re.I)
    def used_to(m):
        before, _after, _ = _near(m.string, m.start(), m.end())
        if before in _YOOST_BEFORE:                             # "I used to", "get used to", "I'm used to"; NOT "a unit used to measure" (that one is yoozd)
            return _case(m.group(1), "yoost") + " " + m.group(2)
        return m.group(0)
    out = re.sub(r"\b(used) (to)\b", used_to, out, flags=re.I)
    out = re.sub(r"\b(no|any|much|little|of|in|its|their|makes|make|made) (use)\b(?! (?:of|the|it|them|to)\b)", lambda m: m.group(1) + " " + _case(m.group(2), "yoos"), out, flags=re.I)

    def content(m):
        before, after, _ = _near(m.string, m.start(), m.end())
        if before in _CONTENT_HAPPY_BEFORE or after in ("with", "to"):
            return _case(m.group(0), "kun-tent")
        return m.group(0)
    out = re.sub(r"\bcontent\b", content, out, flags=re.I)

    def record(m):
        before, _after, _ = _near(m.string, m.start(), m.end())
        if before in _VERB_RECORD_BEFORE:
            return _case(m.group(0), "ri-cord")
        return m.group(0)
    return re.sub(r"\brecord\b", record, out, flags=re.I)


_table = None
_compiled = {}


def _load():
    global _table
    if _table is None:
        try:
            with open(paths.ROOT / "config" / "pronunciations.json", encoding="utf-8") as handle:
                data = json.load(handle)
            _table = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            log.warning("Could not read config/pronunciations.json; hard words are read as written")
            _table = {}
    return _table


def reload():
    global _table
    _table = None
    _compiled.clear()


def _words(voice_name):
    key = voice_name or ""
    if key not in _compiled:
        table = _load()
        merged = {}
        merged.update({k: v for k, v in (table.get("words") or {}).items() if isinstance(v, str)})
        if key:
            merged.update({k: v for k, v in (table.get(key) or {}).items() if isinstance(v, str)})
        if merged:
            pattern = re.compile(r"\b(%s)\b" % "|".join(re.escape(w) for w in sorted(merged, key=len, reverse=True)))
            _compiled[key] = (pattern, merged)
        else:
            _compiled[key] = None
    return _compiled[key]


def _below_hundred(n):
    if n < 20:
        return _ONES[n]
    return _TENS[n // 10] + ("-" + _ONES[n % 10] if n % 10 else "")


def _year_words(year):
    """1994 = 'nineteen ninety-four', 2014 = 'twenty fourteen', 3309 = 'thirty-three oh nine', 2000 = 'two thousand', 3300 = 'thirty-three hundred'."""
    if year % 1000 == 0:
        return "%s thousand" % _ONES[year // 1000]
    high, low = divmod(year, 100)
    if 2000 <= year <= 2009:
        return "two thousand %s" % _ONES[low]
    if low == 0:
        return "%s hundred" % _below_hundred(high)
    if low < 10:
        return "%s oh %s" % (_below_hundred(high), _ONES[low])
    return "%s %s" % (_below_hundred(high), _below_hundred(low))


def _ordinal_words(match):
    n = int(match.group(1))
    if n in _ORDINAL_WORDS:
        return _ORDINAL_WORDS[n]
    if n < 20:
        return _ONES[n] + "th"
    tens, ones = n - n % 10, n % 10
    return _TENS[tens // 10][:-1] + "ieth" if not ones else _below_hundred(tens) + "-" + _ORDINAL_WORDS.get(ones, _ONES[ones] + "th")


def _system_code(match):
    first, single, mass, number, last = match.groups()
    spelled = lambda text: " ".join(text)
    out = "%s dash %s, %s %s" % (spelled(first), single, mass.upper(), spelled(number))
    return out + (" dash %s" % spelled(last) if last else "")


def _spoken_decimal(match):
    return "%s point %s" % (match.group(1), " ".join(match.group(2)))


def _live_word(match):
    """'live' as the verb (liv) or the adjective (lyve); 'lives' as the verb (livz) or the plural of life (lyvz). Left alone when it is not clear."""
    before, word, plural, after = match.group(1), match.group(2), match.group(3), match.group(4)
    prev = (before or "").lower().replace("’", "'")
    nxt = (after or "").lower()
    cap = word[0].isupper()
    if plural:
        if prev in _LIFE_PLURAL_BEFORE:
            new = "lyvz"
        elif prev in ("he", "she", "it", "who", "that", "where", "which", "one", "everyone", "someone", "nobody", "she's") or (not prev and False):
            new = "livz"
        else:
            return match.group(0)
    else:
        if prev in _LIVE_ADJ_BEFORE or (nxt in _LIVE_NOUN_AFTER and prev not in _LIVE_VERB_BEFORE):
            new = "lyve"
        elif prev in _LIVE_VERB_BEFORE:
            new = "liv"
        else:
            return match.group(0)
    if cap:
        new = new.capitalize()
    out = (before + " " if before else "") + new
    return out + ((" " + after) if after else "")


def prepare(text, voice_name=""):
    """The text as it should be handed to the voice. Safe on anything: a failure returns the text unchanged."""
    if not text:
        return text
    try:
        out = _SALUTE.sub("oh seven", text)
        out = _SYSTEM_CODE.sub(_system_code, out)
        out = _YEAR.sub(lambda m: _year_words(int(m.group(1))), out)
        out = _ORDINAL.sub(_ordinal_words, out)
        out = _DECIMAL.sub(_spoken_decimal, out)
        out = _KM.sub(" kilometres", out)
        out = _METRES.sub(" metres", out)
        out = _GEE.sub(" gee", out)
        out = _LIVE.sub(_live_word, out)
        out = _say_heteronyms(out)
        found = _words(voice_name)
        if found is not None:
            pattern, merged = found
            out = pattern.sub(lambda m: merged[m.group(1)], out)
        return out
    except Exception:
        log.debug("Could not prepare the text", exc_info=True)
        return text
