"""
THE EAST ORION COMPANY (EOC) - what she knows about the company, its CEO and the systems it owns.

Ask her:  "tell me about the East Orion Company"   (then "tell me more" takes you round the systems one by one)
          "who is the CEO"      "which systems does the EOC own"      "tell me about Arcadia / Milliways / Payden's Haven"
She knows who YOU are: if your Commander name is on the CEO list she treats you as the boss, and if you built one of the
systems she says so. The facts are in config/eoc.json (edit it as the company grows); her framing words are in
voicepacks/default/eoc.json.
"""
import json
import re
import time

from core import paths
from core.identity import assistant_name, personalise
from core.logger import get_logger
from personality.mood_engine import effective_mood

log = get_logger("eoc")

RECENT_SECONDS = 300.0
_COMPANY = r"(?:east orion(?: company)?|e o c|eoc)"
_ASK = r"(?:tell me (?:about|more about)|what(?: is|s| was)|who(?: is|s| are| were| was)|explain|describe|talk about|give me (?:a tour of|an overview of))"

OVERVIEW = re.compile(r"^(?:%s )?(?:the )?%s(?: company)?(?: again)?$|^%s (?:the )?%s$|^(?:give me )?(?:a )?(?:tour|overview) of (?:the )?%s$"
                      % (_ASK, _COMPANY, _ASK, _COMPANY, _COMPANY))
CEO = re.compile(r"^who(?: is|s) (?:the )?(?:ceo|boss|owner|founder|head|chief)(?: of (?:the )?%s)?$|^who (?:runs|owns|founded|leads|is in charge of) (?:the )?%s$"
                 % (_COMPANY, _COMPANY))
MEMBERS = re.compile(r"\bhow many (?:members|people|pilots|commanders|cmdrs)\b.*\b%s\b|\b%s\b.*\bhow many (?:members|people|pilots|commanders|cmdrs)\b|^how many (?:members|people|pilots) (?:do we have|are there|are in the company|are in the squadron|in the squadron)$" % (_COMPANY, _COMPANY))
RANK_LIST = re.compile(r"^(?:who(?: is|s| are)|list|name|tell me about|show me) (?:all )?(?:the )?(?P<rank>[a-z ]+?)s?(?: in the (?:company|squadron|eoc))?$")
LISTING = re.compile(r"\b%s\b.*\b(?:systems?|territory|empire|space|places|stations)\b|\b(?:systems?|stations)\b.*\b%s\b" % (_COMPANY, _COMPANY))
ENTRY_LEAD = re.compile(r"^(?:%s|where(?: is|s)|show me|do you know|what do you know about|anything on) " % _ASK)


def clean(text):
    text = re.sub(r"['’]", "", (text or "").lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", text)).strip()


def same_person(a, b):
    """'CMDR Ben Can-Obi' and 'ben can obi' are the same person."""
    def tidy(name):
        name = re.sub(r"^(?:cmdr|commander)\s+", "", str(name or "").strip(), flags=re.I)
        return re.sub(r"[^a-z0-9]", "", name.lower())
    return bool(tidy(a)) and tidy(a) == tidy(b)


_LETTERS = re.compile(r"^[A-Za-z]{1,3}$")


def speakable(name):
    """'Wregoe JU-E c25-18' -> 'Wregoe J U, E, C 25, 18' so she reads the code out letter by letter."""
    out, previous_code = "", False
    for word in str(name or "").split():
        code = False
        if word.upper() in ("HIP", "NGC", "HD", "LHS", "LTT"):
            spoken = " ".join(word.upper())
        elif "-" in word or (re.search(r"\d", word) and re.search(r"[A-Za-z]", word)):
            code = True
            pieces = []
            for part in [p for p in word.split("-") if p]:
                match = re.match(r"^([A-Za-z]+)(\d+)$", part)
                if match:
                    pieces.append(" ".join(match.group(1).upper()) + " " + match.group(2))
                elif part.isdigit():
                    pieces.append(part)
                elif _LETTERS.match(part):
                    pieces.append(" ".join(part.upper()))
                else:
                    pieces.append(part)
            spoken = ", ".join(pieces)
        else:
            spoken = word
        out += (", " if (code and previous_code) else (" " if out else "")) + spoken
        previous_code = code
    return out


def sound(text):
    """A rough 'how it sounds' spelling, so a mis-heard name still matches ('nix evera' ~ 'Nyx Evera', 'curd nerd' ~ 'CurdNerd')."""
    t = re.sub(r"[^a-z]", "", str(text or "").lower())
    for old, new in (("ph", "f"), ("ck", "k"), ("ks", "x"), ("x", "x"), ("c", "k"), ("q", "k"), ("z", "s"), ("y", "i"), ("w", "v")):
        t = t.replace(old, new)
    t = re.sub(r"[aeiou]+", "a", t)
    return re.sub(r"(.)\1+", r"\1", t)


def similarity(a, b):
    import difflib
    return difflib.SequenceMatcher(None, sound(a), sound(b)).ratio()


class EOCTeller:
    def __init__(self, speech, dialogue, settings, state_provider=None, path=None, clock=time.monotonic, rng=None):
        import random
        self.speech = speech
        self.dialogue = dialogue
        self.settings = settings
        self.state_provider = state_provider or (lambda: None)
        self.clock = clock
        self.rng = rng or random.Random()
        self.path = path or (paths.CONFIG_DIR / "eoc.json")
        self.data = {"ceo": [], "pilots": [], "systems": [], "home": "", "ranks": []}
        self.last_told = None
        self.tour = 0                         # which system "tell me more" says next
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                self.data["ceo"] = [str(x) for x in data.get("ceo", []) if x]
                self.data["pilots"] = [p for p in data.get("pilots", []) if isinstance(p, dict) and p.get("name")]
                self.data["systems"] = [s for s in data.get("systems", []) if isinstance(s, dict) and s.get("title")]
                self.data["home"] = str(data.get("home") or "")
                self.data["ranks"] = [str(r) for r in data.get("ranks", []) if r]
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            log.exception("Could not read %s", self.path)

    # ---- who is who ----
    def commander(self):
        return getattr(self.state_provider(), "commander", None)

    def player_is_ceo(self):
        me = self.commander()
        return bool(me) and any(same_person(me, name) for name in self.data["ceo"])

    def player_systems(self):
        me = self.commander()
        return [s for s in self.data["systems"] if me and same_person(me, s.get("architect"))]

    def player_pilot(self):
        me = self.commander()
        return next((p for p in self.data["pilots"] if me and same_person(me, p.get("name"))), None)

    def find_system(self, tidy):
        """The system whose name, architect or station is in the sentence (longest match wins)."""
        best, best_len = None, 0
        for system in self.data["systems"]:
            names = list(system.get("aliases", [])) + [system.get("title", ""), system.get("architect", "")]
            for name in names:
                name = clean(name)
                if name and re.search(r"\b%s\b" % re.escape(name), tidy) and len(name) > best_len:
                    best, best_len = system, len(name)
        return best

    def find_pilot(self, tidy):
        """
        The roster member named in the sentence. Tries, in order: the full name written out, the full name with the
        spaces squashed ('curd nerd' = CurdNerd), one name on its own ('nyx'), then a close sound-alike (speech
        recognition often hears 'nix' for 'nyx'). Returns None when nothing is close.
        """
        pilots = self.data["pilots"]
        phrase = ENTRY_LEAD.sub("", tidy, count=1)
        phrase = re.sub(r"^(?:the )?(?:commander |cmdr |captain |admiral |fleet admiral |commodore )", "", phrase).strip()
        squashed = phrase.replace(" ", "")
        best, best_len = None, 0
        for pilot in pilots:                                     # 1 and 2: the whole name, as written or squashed
            name = clean(pilot.get("name"))
            if len(name) < 3:
                continue
            if (re.search(r"\b%s\b" % re.escape(name), tidy) or name.replace(" ", "") == squashed) and len(name) > best_len:
                best, best_len = pilot, len(name)
        if best is not None:
            return best
        if not phrase:
            return None
        words = phrase.split()
        for pilot in pilots:                                     # 3: one name of theirs on its own ("nyx", "curd")
            parts = [p for p in clean(pilot.get("name")).split() if len(p) >= 3 and p not in ("the", "cpt", "capt", "doc")]
            if len(words) <= 2 and any(w == p for w in words for p in parts):
                matches = [q for q in pilots if any(w == p for w in words for p in clean(q.get("name")).split() if len(p) >= 3)]
                if len(matches) == 1:
                    return pilot
        scored = []                                              # 4: sounds like
        for pilot in pilots:
            name = clean(pilot.get("name"))
            candidates = [name] + [p for p in name.split() if len(p) >= 4]
            top = max(similarity(c, phrase) for c in candidates)
            scored.append((top, pilot))
        scored.sort(key=lambda item: -item[0])
        if scored and scored[0][0] >= 0.8 and (len(scored) < 2 or scored[0][0] - scored[1][0] >= 0.05):
            return scored[0][1]
        if scored and scored[0][0] >= 0.6:
            log.info("No roster match for %r (closest: %s, %.2f)", phrase, scored[0][1].get("name"), scored[0][0])
        return None

    def rank_of(self, name):
        pilot = next((p for p in self.data["pilots"] if same_person(name, p.get("name"))), None)
        return pilot.get("rank") if pilot else None

    def rank_group(self, tidy):
        """'who are the admirals' -> ('Admiral', [pilots]); None when it isn't a rank."""
        match = RANK_LIST.match(tidy)
        if not match:
            return None
        wanted = match.group("rank").strip()
        for rank in sorted(self.data["ranks"], key=len, reverse=True):
            low = clean(rank)
            if wanted in (low, low + "s") or wanted == low.rstrip("s"):
                return rank, [p for p in self.data["pilots"] if p.get("rank") == rank]
        return None

    def home(self):
        return next((s for s in self.data["systems"] if s.get("id") == self.data["home"]), None) or (
            self.data["systems"][0] if self.data["systems"] else None)

    # ---- asking ----
    def recent(self):
        return self.last_told is not None and self.clock() - self.last_told <= RECENT_SECONDS

    def try_handle(self, text):
        """Answer a question about the company. Returns what she said, or None when this wasn't about the company."""
        if self.dialogue is None or not self.data["systems"]:
            return None
        tidy = clean(text)
        tidy = re.sub(r"^(?:hey |hi |ok |okay )?(?:starling )?(?:please )?", "", tidy)
        tidy = re.sub(r"(?: please| starling| commander)+$", "", tidy)
        if not tidy:
            return None
        if CEO.match(tidy):
            return self.say_ceo()
        if OVERVIEW.match(tidy):
            return self.say_overview()
        if MEMBERS.search(tidy):
            return self.say_members()
        group = self.rank_group(tidy)
        if group is not None and group[1]:
            return self.say_rank(*group)
        if LISTING.search(tidy) and re.match(r"^(?:which|what|list|name|how many|where|tell me|show me|give me|does|do)\b", tidy):
            return self.say_list()
        if ENTRY_LEAD.match(tidy):
            pilot = self.find_pilot(tidy)
            if pilot is not None:
                return self.say_pilot(pilot)
            system = self.find_system(tidy)
            if system is not None:
                return self.say_system(system)
        return None

    # ---- saying ----
    def _mood(self):
        if self.settings.get("personality.style", "personality") != "personality":
            return ""
        return effective_mood(self.settings) or ""

    def _pick(self, key, values=None):
        allow = bool(self.settings.get("speech.allow_mature", False))
        for _ in range(8):
            line = self.dialogue.pick(key, self._mood(), allow, False)
            if line is None:
                return None
            try:
                return line.text.format(**(values or {}))
            except (KeyError, IndexError, ValueError):
                continue
        return None

    def _say(self, text):
        text = personalise(text.replace("{name}", assistant_name(self.settings)), self.settings)
        if self.speech is not None and self.settings.get("speech.enabled", True):
            self.speech.say(text=text, priority="normal", event_name="eoc")
        self.last_told = self.clock()
        return text.replace("||", " ")

    def _ceo_name(self):
        return self.data["ceo"][0] if self.data["ceo"] else "the CEO"

    def say_overview(self):
        self.tour = 0
        home = self.home()
        values = {"count": len(self.data["systems"]), "ceo": self._ceo_name(), "home": home["title"] if home else "home"}
        parts = [self._pick("EOC_Overview", values)]
        if self.player_is_ceo():
            parts.append(self._pick("EOC_Overview_CEO", values))
        else:
            parts.append(self._pick("EOC_Overview_Boss", values))
        rank = self.rank_of(self.commander()) if self.commander() else None
        if rank and not self.player_is_ceo():
            parts.append(self._pick("EOC_YouAre", {"rank": rank}))
        parts.append(self._pick("EOC_TourOffer", values))
        text = "||".join(p for p in parts if p)
        return self._say(text) if text else None

    def say_ceo(self):
        if self.player_is_ceo():
            text = self._pick("EOC_CEO_You", {"ceo": self._ceo_name()})
        else:
            home = self.home()
            text = self._pick("EOC_CEO", {"ceo": self._ceo_name(), "home": home["title"] if home else "home"})
        return self._say(text) if text else None

    def say_list(self):
        names = [s["title"] for s in self.data["systems"]]
        joined = ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0]
        text = self._pick("EOC_List", {"count": len(names), "names": joined})
        return self._say(text) if text else None

    def say_system(self, system, intro=True):
        me_built = self.commander() and same_person(self.commander(), system.get("architect"))
        parts = []
        if intro:
            parts.append(self._pick("EOC_SystemIntro", {"title": system["title"]}))
        parts.append(system.get("say") or speakable(system.get("system", "")))
        who = system.get("architect")
        if who:
            parts.append(self._pick("EOC_BuiltByYou" if me_built else "EOC_BuiltBy", {"architect": who, "title": system["title"]}))
        if system.get("blurb"):
            parts.append(system["blurb"])
        text = "||".join(p for p in parts if p)
        return self._say(text) if text else None

    @staticmethod
    def _spoken_name(pilot):
        return pilot.get("say") or re.sub(r"\.$", "", str(pilot.get("name", "")))

    def say_pilot(self, pilot):
        built = [s for s in self.data["systems"] if same_person(pilot.get("name"), s.get("architect"))]
        you = self.commander() and same_person(self.commander(), pilot.get("name"))
        rank = pilot.get("rank") or "member"
        ceo = any(same_person(pilot.get("name"), c) for c in self.data["ceo"])
        parts = [self._pick("EOC_PilotYou" if you else "EOC_Pilot", {"name": self._spoken_name(pilot), "rank": rank})]
        if ceo:
            parts.append(self._pick("EOC_PilotCEO", {"name": self._spoken_name(pilot)}))
        if built:
            parts.append(self._pick("EOC_PilotBuilt", {"titles": " and ".join(s["title"] for s in built)}))
            if built[0].get("blurb"):
                parts.append(built[0]["blurb"])
        text = "||".join(p for p in parts if p)
        return self._say(text) if text else None

    def say_members(self):
        pilots = self.data["pilots"]
        if not pilots:
            return None
        top = [p for p in pilots if p.get("rank") == (self.data["ranks"][0] if self.data["ranks"] else None)]
        text = self._pick("EOC_Members", {"count": len(pilots), "ranks": len(self.data["ranks"])})
        return self._say(text) if text else None

    def say_rank(self, rank, pilots):
        names = [self._spoken_name(p) for p in pilots]
        shown = names[:8]
        joined = ", ".join(shown[:-1]) + " and " + shown[-1] if len(shown) > 1 else shown[0]
        extra = len(names) - len(shown)
        text = self._pick("EOC_RankList", {"rank": rank + ("" if len(pilots) == 1 else "s"), "count": len(pilots), "names": joined,
                                          "more": (", and %d more" % extra) if extra > 0 else ""})
        return self._say(text) if text else None

    def next(self):
        """'Tell me more' after a company answer: the next system on the tour."""
        systems = self.data["systems"]
        if not systems:
            return None
        if self.tour >= len(systems):
            self.tour = 0
            text = self._pick("EOC_TourEnd")
            return self._say(text) if text else None
        system = systems[self.tour]
        self.tour += 1
        return self.say_system(system)
