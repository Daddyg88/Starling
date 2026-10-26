"""
Exobiology guesses: what could be living on a planet, and what it might be worth.

How it works (all from your own journal, nothing is looked up online):
  1. Scan events tell her each body's atmosphere, gravity, temperature, volcanism and the stars / planets in the system.
  2. FSSBodySignals says "this body has N biological signals" (N = how many different genera live there).
  3. config/bio_rules.json says where each species can live (see the credit inside that file).
     Every species whose rules fit the body is a candidate. The value is worked out from the candidates.
  4. After the surface scan (SAASignalsFound) the real genera are known, so the guess is corrected.
     After you scan a creature (ScanOrganic) the real species is known.
  5. When you leave the system everything is forgotten (reset), so this never grows.

The rules are a guess, not a promise: the game does not say what lives where, and the community data is itself measured.
"""

import json
import re
import threading
from pathlib import Path

from core import paths
from core.logger import get_logger
from events._signals import count_signals
from journal.exobiology import ExobiologyTracker, spoken_credits, _read_json, _write_json

log = get_logger("bio_predict")

MAX_BODIES = 80
_rules_cache = {}


def norm(text):
    """'Carbon dioxide-rich' -> 'carbondioxiderich', 'Rocky body' -> 'rocky'."""
    text = re.sub(r"\bbody\b", "", str(text or "").lower())
    return re.sub(r"[^a-z]", "", text)


# Species that exist in only one place in the galaxy (Radicoida Unica was found in a single system). They are never
# guessed and never taught to the learner (it would only teach her wrong habits), but they count for the codex.
UNIQUE_SPECIES = {"radicoida unica": "Radicoida"}


def genus_key(text):
    key = re.sub(r"[^a-z]", "", str(text or "").lower())
    return key[:-1] if key.endswith("s") else key


def same_genus(a, b):
    a, b = genus_key(a), genus_key(b)
    return bool(a and b and (a in b or b in a))


def load_rules(path=None):
    path = Path(path or paths.CONFIG_DIR / "bio_rules.json")
    if path not in _rules_cache:
        data = _read_json(path)
        _rules_cache[path] = [r for r in data.get("species", []) if isinstance(r, dict) and r.get("n")]
    return _rules_cache[path]


def short_body(name, system):
    """'Synuefe AB-C d1 A 3' -> 'A 3' (the system name is not worth saying)."""
    name, system = str(name or ""), str(system or "")
    if system and name.lower().startswith(system.lower()):
        name = name[len(system):].strip()
    return name or "that planet"


# ---------------------------------------------------------------- codex knowledge
class BioCodex:
    """Which biological species are already in your codex. Kept in data/bio_codex.json."""

    def __init__(self, path=None):
        self.path = Path(path) if path else None
        data = _read_json(self.path) if self.path else {}
        self.known = {str(s).lower() for s in data.get("species", []) if s}
        self.history_done = bool(data.get("history_done"))
        self._lock = threading.Lock()

    def has(self, species):
        return str(species or "").lower() in self.known

    def add(self, species):
        key = str(species or "").lower().strip()
        if key and key not in self.known:
            self.known.add(key)
            self.save()

    def save(self):
        if self.path:
            with self._lock:
                _write_json(self.path, {"species": sorted(self.known), "history_done": self.history_done})

    def scan_history(self, folder, rules=None):
        """One-off: reads your old journal files for codex finds and finished samples. Run it in a background thread."""
        if self.history_done or not folder:
            return
        names = {r["n"].lower() for r in (rules if rules is not None else load_rules())} | set(UNIQUE_SPECIES)
        try:
            files = sorted(Path(folder).glob("Journal*.log"))
        except OSError:
            return
        for file in files:
            try:
                with open(file, "r", encoding="utf-8", errors="replace") as handle:
                    for line in handle:
                        if "CodexEntry" not in line and "ScanOrganic" not in line:
                            continue
                        try:
                            entry = json.loads(line)
                        except ValueError:
                            continue
                        self._from_entry(entry, names, save=False)
            except OSError:
                continue
        self.history_done = True
        self.save()

    def _from_entry(self, entry, names, save=True):
        kind = entry.get("event")
        if kind == "CodexEntry":
            species = str(entry.get("Name_Localised") or "").split(" - ")[0].strip().lower()
        elif kind == "ScanOrganic" and entry.get("ScanType") == "Analyse":
            species = str(entry.get("Species_Localised") or "").strip().lower()
        else:
            return
        if species in names:
            if save:
                self.add(species)
            else:
                self.known.add(species)


# ---------------------------------------------------------------- what she has learned
class BioLearned:
    """
    What the surface scans have taught her (data/bio_learned.json). Two things:
      * stats[genus] = how often a genus was a candidate ("seen") and how often it was really there ("hit").
        The hit rate decides which genera she names first and how the value is averaged.
      * envelopes[genus] = the kinds of planet the genus was REALLY found on (planet class, atmosphere, temperature, gravity,
        volcanism). If the rules missed it, a planet inside that envelope now counts as a candidate too.
    Each planet is counted once (a list of "system|planet" keys), so replaying a journal does not count twice.
    """
    MAX_SEEN = 3000

    def __init__(self, path=None):
        self.path = Path(path) if path else None
        data = _read_json(self.path) if self.path else {}
        self.stats = {k: v for k, v in (data.get("stats") or {}).items() if isinstance(v, dict)}
        self.envelopes = {k: v for k, v in (data.get("envelopes") or {}).items() if isinstance(v, dict)}
        self.seen = list(data.get("seen") or [])
        self._seen_set = set(self.seen)

    def save(self):
        if self.path:
            _write_json(self.path, {"stats": self.stats, "envelopes": self.envelopes, "seen": self.seen[-self.MAX_SEEN:]})

    def weight(self, genus):
        """0..1: how likely a candidate genus really turns up (starts at one half, learns from every surface scan)."""
        s = self.stats.get(genus_key(genus)) or {}
        return (s.get("hit", 0) + 1.0) / (s.get("seen", 0) + 2.0)

    def observe(self, key, props, candidate_genera, real_genera):
        """One surface scan: which genera were possible, which were there. Returns True if it was new."""
        if not key or key in self._seen_set:
            return False
        self._seen_set.add(key)
        self.seen.append(key)
        for g in candidate_genera:
            entry = self.stats.setdefault(genus_key(g), {"seen": 0, "hit": 0})
            entry["seen"] += 1
            if any(same_genus(g, r) for r in real_genera):
                entry["hit"] += 1
        for g in real_genera:
            if genus_key(g) in {genus_key(v) for v in UNIQUE_SPECIES.values()}:
                continue                                                    # one-of-a-kind: nothing to learn from where it grew
            if not any(same_genus(g, c) for c in candidate_genera):        # one the rules did not expect: it was there, so count it
                entry = self.stats.setdefault(genus_key(g), {"seen": 0, "hit": 0})
                entry["seen"] += 1
                entry["hit"] += 1
            if props is None:
                continue
            env = self.envelopes.setdefault(genus_key(g), {"n": 0, "pc": [], "atm": [], "volc": [], "thin": []})
            env["n"] += 1
            for field, value in (("pc", props["pc"]), ("atm", props["atm"]), ("volc", bool(props["volc"])), ("thin", bool(props["thin"]))):
                if value not in env[field]:
                    env[field].append(value)
            for field, value, pick in (("kmin", props["k"], min), ("kmax", props["k"], max), ("gmax", props["g"], max)):
                if isinstance(value, (int, float)):
                    env[field] = value if field not in env else pick(env[field], value)
        self.save()
        return True

    def fits(self, genus, props):
        """True when a planet looks like the ones this genus was really found on."""
        env = self.envelopes.get(genus_key(genus))
        if not env or not props:
            return False
        if props["pc"] not in env["pc"] or props["atm"] not in env["atm"] or bool(props["thin"]) not in env["thin"]:
            return False
        if bool(props["volc"]) not in env["volc"]:
            return False
        k, g = props["k"], props["g"]
        if k is not None and "kmin" in env and not (env["kmin"] <= k <= env["kmax"]):
            return False
        if g is not None and "gmax" in env and g > env["gmax"] + 0.0005:
            return False
        return True


# ---------------------------------------------------------------- one body
class BioBody:
    def __init__(self, name, short, count):
        self.name = name
        self.short = short
        self.count = count                 # how many biological signals (= genera) it has
        self.candidates = []               # rules that fit
        self.genera = []                   # real genera, once the surface scan is done
        self.species = []                  # real species, once you scanned them
        self.guessed_genera = []           # what she guessed from the FSS (to say "I was right/wrong")
        self.known_props = True            # False when she never saw this body's own scan
        self.awaiting = False              # the FSS signals came first; the guess waits for the body's own Scan (it follows a line later)
        self.geo = False
        self.body_id = None
        self.done = []                     # species (lower case) you have finished sampling here: all three samples
        self.done_genera = []

    def candidate_genera(self):
        seen = []
        for r in self.candidates:
            if r["g"] not in seen:
                seen.append(r["g"])
        return seen


class BioPredictor:
    def __init__(self, tracker=None, codex=None, settings=None, rules=None, learned=None):
        self._tracker = tracker
        self.codex = codex or BioCodex()
        self.learned = learned or BioLearned()
        self.settings = settings
        self._rules = rules
        self.reset()

    # ---- helpers ----
    @property
    def rules(self):
        if self._rules is None:
            self._rules = load_rules()
        return self._rules

    @property
    def tracker(self):
        if self._tracker is None:
            self._tracker = ExobiologyTracker(paths.CONFIG_DIR / "exobiology_values.json")
        return self._tracker

    def _on(self, key, default=True):
        try:
            return bool(self.settings.get(key, default)) if self.settings is not None else default
        except Exception:
            return default

    def reset(self):
        """Forget the system (called when you jump away)."""
        self.props = {}            # body name -> facts from its Scan
        self.ids = {}              # BodyID -> body name
        self.stars = set()         # first letters of the star classes seen, lower case ("a", "m", "n"...)
        self.classes = set()       # normalised planet classes seen in the system
        self.bodies = {}           # body name -> BioBody
        self.system = ""
        self.spoken = 0
        self.hinted = set()
        self.hidden = False        # "hide the bio overlay" (voice); shown again in the next system
        self.focus = ""            # the planet the overlay is showing in detail (after you map it), "" = show the list
        self.focus_targeted = False   # has the game's target been that planet since we focused it?

    # ---- journal input ----
    def set_system(self, name):
        if name and name != self.system:
            self.reset()
            self.system = name

    def note_scan(self, entry):
        """A body was scanned. Returns events to announce: the guess for a planet whose FSS signals came just before it."""
        name = entry.get("BodyName")
        if not name:
            return []
        star = entry.get("StarType")
        if star:
            star = str(star).lower()
            self.stars.add("h" if star.startswith("ae") else star[0])
            return []
        pc = entry.get("PlanetClass")
        if not pc:
            return []
        if len(self.props) >= MAX_BODIES * 3:
            return []
        self.classes.add(norm(pc))
        gravity = entry.get("SurfaceGravity")
        self.props[name] = {
            "pc": norm(pc),
            "atm": norm(entry.get("AtmosphereType")) or "none",
            "thin": "thin" in str(entry.get("Atmosphere") or "").lower(),
            "g": float(gravity) / 9.80665 if isinstance(gravity, (int, float)) else None,
            "k": entry.get("SurfaceTemperature") if isinstance(entry.get("SurfaceTemperature"), (int, float)) else None,
            "volc": str(entry.get("Volcanism") or "").lower(),
            "ls": entry.get("DistanceFromArrivalLS"),
            "addr": entry.get("SystemAddress"),
            "id": entry.get("BodyID"),
        }
        if entry.get("BodyID") is not None:
            self.ids[entry["BodyID"]] = name
        body = self.bodies.get(name)
        if body is not None and body.awaiting:
            body.awaiting = False
            body.known_props = True
            body.candidates = self.candidates_for(name, geo=body.geo)
            body.guessed_genera = body.candidate_genera()
            return self._guess_events(body)
        return []

    def note_codex(self, entry):
        self.codex._from_entry(entry, {r["n"].lower() for r in self.rules})

    # ---- fitting the rules ----
    def fits(self, rule, p, geo=False):
        if rule.get("p") and p["pc"] not in rule["p"]:
            return False
        atmos = rule.get("a")
        if atmos is not None and p["atm"] not in atmos:
            return False
        if rule.get("thin") and not p["thin"]:
            return False
        if atmos and "none" in atmos and p["atm"] != "none" and not p["thin"]:
            return False
        if "gmax" in rule and p["g"] is not None and p["g"] > rule["gmax"] + 0.0005:
            return False
        k = p["k"]
        if k is not None:
            if "tmin" in rule and k < rule["tmin"]:
                return False
            if "tmax" in rule and k > rule["tmax"]:
                return False
            link = rule.get("lk")
            if link and p["atm"] in link["a"]:
                if link.get("tmin") is not None and k < link["tmin"]:
                    return False
                if link.get("tmax") is not None and k > link["tmax"]:
                    return False
        if rule.get("v") and not any(word in p["volc"] for word in rule["v"]):
            return False
        if rule.get("vreq") and not p["volc"]:
            return False
        if rule.get("geo") and not geo:
            return False
        if rule.get("stars") and self.stars and not (set(rule["stars"]) & self.stars):
            return False
        if rule.get("sys") and not (set(rule["sys"]) & self.classes):
            return False
        if rule.get("lsmin") and isinstance(p.get("ls"), (int, float)) and p["ls"] < rule["lsmin"]:
            return False
        return True

    def candidates_for(self, name, geo=False):
        p = self.props.get(name)
        if p is None:
            return []
        found = [r for r in self.rules if self.fits(r, p, geo)]
        have = {genus_key(r["g"]) for r in found}
        for key in self.learned.envelopes:           # genera the rules missed but she has really seen on planets like this
            if key not in have and self.learned.fits(key, p):
                extra = [r for r in self.rules if same_genus(r["g"], key)]
                found.extend(extra)
                have.add(key)
        return found

    # ---- values ----
    def species_value(self, rule_or_name):
        name = rule_or_name["n"] if isinstance(rule_or_name, dict) else rule_or_name
        return self.tracker.base_value(name)

    def estimate(self, body):
        """(low, expected, high) credits for the body, or None when no price is known. Uses the real genera when known."""
        groups = {}
        for r in body.candidates:
            if body.genera and not any(same_genus(r["g"], g) for g in body.genera):
                continue
            value = self.species_value(r)
            if value:
                groups.setdefault(r["g"], []).append(value)
        if not groups:
            return None
        means = sorted((sum(v) / len(v) for v in groups.values()), reverse=True)
        lows = sorted((min(v) for v in groups.values()))
        highs = sorted((max(v) for v in groups.values()), reverse=True)
        count = max(1, min(body.count, len(means)))
        if body.genera:
            expected = sum(means[:count])
        else:        # before the surface scan: average, weighted by how often each genus has really been there
            weights = {g: self.learned.weight(g) for g in groups}
            total = sum(weights.values()) or 1.0
            expected = sum(weights[g] * (sum(v) / len(v)) for g, v in groups.items()) / total * count
        mult = self.footfall_multiplier(body)
        return (sum(lows[:count]) * mult, expected * mult, sum(highs[:count]) * mult)

    def footfall_multiplier(self, body):
        """5 when nobody had set foot on the planet before you (the game's first footfall bonus), otherwise 1."""
        p = self.props.get(body.name) or {}
        try:
            first = self.tracker.footfall.get((p.get("addr"), p.get("id"))) is False
            return self.tracker.multiplier if first else 1
        except Exception:
            return 1

    def worth(self, body):
        if body.species:
            return sum(self.species_value(s) or 0 for s in body.species) * self.footfall_multiplier(body)
        est = self.estimate(body)
        return int(est[1]) if est else 0

    def top_candidates(self, body):
        found = []
        for r in body.candidates:
            if body.genera and not any(same_genus(r["g"], g) for g in body.genera):
                continue
            if self.tracker.is_top(r["n"]):
                found.append(r)
        return sorted(found, key=lambda r: -(self.species_value(r) or 0))

    # ---- codex flags ----
    def new_flags(self, body):
        """How many of the body's signals could be something you do not have in your codex yet."""
        if body.species:
            return sum(1 for s in body.species if not self.codex.has(s))
        groups = {}
        for r in body.candidates:
            if body.genera and not any(same_genus(r["g"], g) for g in body.genera):
                continue
            groups.setdefault(r["g"], []).append(r["n"])
        fresh = sum(1 for names in groups.values() if any(not self.codex.has(n) for n in names))
        return min(fresh, body.count) if not body.genera else min(fresh, len(body.genera))

    # ---- the journal events ----
    def _body(self, name, count, system=""):
        body = self.bodies.get(name)
        if body is None:
            if len(self.bodies) >= MAX_BODIES:
                self.bodies.pop(next(iter(self.bodies)))
            body = self.bodies[name] = BioBody(name, short_body(name, system or self.system), count)
        body.count = count or body.count
        body.known_props = name in self.props
        return body

    def note_fss(self, entry, state_system=""):
        """FSSBodySignals. Returns (body, events) where events is a list of (event name, data) to announce."""
        counts = count_signals(entry.get("Signals"))
        if not counts["Biological"]:
            return None, []
        name = entry.get("BodyName")
        body = self._body(name, counts["Biological"], state_system)
        if entry.get("BodyID") is not None:
            self.ids[entry["BodyID"]] = name
        body.geo = counts["Geological"] > 0
        if name not in self.props:
            # the game writes FSSBodySignals one line BEFORE the body's Scan (seen in real journals): wait for it
            body.awaiting, body.candidates, body.guessed_genera = True, [], []
            return body, []
        body.awaiting = False
        body.candidates = self.candidates_for(name, geo=body.geo)
        body.guessed_genera = body.candidate_genera()
        return body, self._guess_events(body)

    def _guess_events(self, body):
        events = []
        if not self._on("exobiology.guess", True):
            return events
        signals = "%s biological %s" % (_number(body.count), "signal" if body.count == 1 else "signals")
        genera = _top_genera(self, body, 3)
        if self.spoken >= 5:
            return events
        self.spoken += 1
        est = self.estimate(body)
        data = {"Body": body.short, "Signals": signals, "Count": body.count}
        if not genera or not est:
            data["Unknown"] = True
        else:
            data["Guess"] = _join_or(genera)
            data["Worth"] = spoken_credits(est[1])
        events.append(("BioGuess", data))
        events.extend(self._top_hint(body))
        return events

    def _top_hint(self, body):
        if not self._on("exobiology.top_hint", True) or len(self.hinted) >= 3:
            return []
        for r in self.top_candidates(body):
            if r["n"] in self.hinted:
                continue
            self.hinted.add(r["n"])
            return [("BioTopHint", {"Species": r["n"], "Body": body.short, "Worth": spoken_credits(self.species_value(r) or 0)})]
        return []

    def note_saa(self, entry, state_system=""):
        """SAASignalsFound: the real genera. Returns events to announce."""
        counts = count_signals(entry.get("Signals"))
        genera = [str(g.get("Genus_Localised") or "") for g in entry.get("Genuses") or [] if isinstance(g, dict)]
        genera = [g for g in genera if g]
        if not counts["Biological"] and not genera:
            return []
        name = entry.get("BodyName")
        body = self.bodies.get(name)
        fresh = body is None
        body = self._body(name, counts["Biological"] or len(genera), state_system)
        if entry.get("BodyID") is not None:
            self.ids[entry["BodyID"]] = name
        if fresh or not body.candidates:
            body.candidates = self.candidates_for(name, geo=counts["Geological"] > 0)
            body.guessed_genera = body.candidate_genera()
        body.genera = genera
        if entry.get("BodyID") is not None:
            body.body_id = entry["BodyID"]
        if genera:
            self.focus, self.focus_targeted = name, False      # the overlay switches to this planet until you target something else
        if genera and body.known_props:
            self.learned.observe("%s|%s" % (self.system or state_system, name), self.props.get(name), body.guessed_genera, genera)
        if not genera or not self._on("exobiology.guess", True):
            return []
        right = all(any(same_genus(g, c) for c in body.guessed_genera) for g in genera)
        mine = [r for r in body.candidates if any(same_genus(r["g"], g) for g in genera)]
        # the surface scan names genera the rules did not allow: show them anyway, priced at their average
        for g in genera:
            if not any(same_genus(r["g"], g) for r in body.candidates):
                body.candidates.extend(r for r in self.rules if same_genus(r["g"], g))
        data = {"Body": body.short, "Right": right or fresh, "Found": _join_and(genera)}
        est = self.estimate(body)
        if est:
            data["Worth"] = spoken_credits(est[1])
        if not est:
            return []
        events = [("BioRefined", data)]
        events.extend(self._top_hint(body))
        return events

    def note_organic(self, entry):
        """ScanOrganic: the first sample tells us the real species on that body. Returns events to announce."""
        species = str(entry.get("Species_Localised") or "").strip()
        if not species:
            return []
        name = self.ids.get(entry.get("Body"))
        body = self.bodies.get(name) if name else None
        if body is not None and species not in body.species:
            body.species.append(species)
        events = []
        if species.lower() in UNIQUE_SPECIES and entry.get("ScanType") == "Log":
            events.append(("UniqueBio", {"Species": species, "Body": body.short if body else ""}))
        if entry.get("ScanType") == "Analyse":
            if body is not None and species.lower() not in body.done:
                body.done.append(species.lower())
                if entry.get("Genus_Localised"):
                    body.done_genera.append(str(entry["Genus_Localised"]))
            fresh = not self.codex.has(species)
            self.codex.add(species)
            if fresh and species.lower() not in UNIQUE_SPECIES and self._on("exobiology.progress", True):
                events.append(("BioProgress", self.progress(species)))
        return events

    def progress(self, species):
        """How far the codex has got: the number of species and the genera never sampled (named only when few are left)."""
        known = {k for k in self.codex.known}
        have = {genus_key(r["g"]) for r in self.rules if r["n"].lower() in known}
        left = []
        for r in self.rules:
            if genus_key(r["g"]) not in have and r["g"] not in left:
                left.append(r["g"])
                have.add(genus_key(r["g"]))
        data = {"Species": species, "Count": len(known), "Left": len(left)}
        if 0 < len(left) <= 3:
            data["Missing"] = _join_and(left)
        return data

    # ---- for the overlay ----
    def note_target(self, body_id):
        """Status.json says which body is targeted now (None = nothing). The detailed view stays while that planet is the target,
        and also while the target does not change (you are landing). Targeting another body, or un-targeting it, goes back to the list."""
        body = self.bodies.get(self.focus) if self.focus else None
        if body is None:
            self.focus = ""
            return
        if body.body_id is not None and body_id == body.body_id:
            self.focus_targeted = True
        elif body_id is None or body_id == 0:
            if self.focus_targeted:
                self.focus = ""
        else:
            self.focus = ""

    def focus_view(self):
        """What the detailed view shows: the planet and one line per life form, or None when the list should be shown."""
        body = self.bodies.get(self.focus) if self.focus else None
        if body is None or not body.genera:
            return None
        mult = self.footfall_multiplier(body)
        lives = []
        for genus in body.genera:
            species = next((s for s in body.species if same_genus(genus, self._genus_of(s))), "")
            options = [r for r in self.rules if same_genus(r["g"], genus)]
            if species:
                base = self.species_value(species) or 0
                new = not self.codex.has(species)
                done = species.lower() in body.done
            else:
                values = [self.species_value(r) for r in options if self.species_value(r)]
                base = sum(values) / len(values) if values else 0
                new = any(not self.codex.has(r["n"]) for r in options) if options else True
                done = False
            lives.append({"name": species or genus, "new": bool(new), "done": done, "value": int(base * mult),
                          "exact": bool(species)})
        return {"body": body.short, "kind": (self.props.get(body.name) or {}).get("pc", "rocky"), "lives": lives}

    def _genus_of(self, species):
        for r in self.rules:
            if r["n"].lower() == str(species).lower():
                return r["g"]
        return str(species).split(" ")[0]

    def rows(self):
        """One dictionary per body with life, in the order she found them."""
        out = []
        for body in self.bodies.values():
            est = self.estimate(body)
            out.append({"body": body.short, "count": body.count, "value": self.worth(body) or (int(est[1]) if est else 0),
                        "new": self.new_flags(body), "kind": (self.props.get(body.name) or {}).get("pc", "rocky"), "known": bool(body.species or body.genera),
                        "species": list(body.species), "genera": list(body.genera)})
        return out


# ---------------------------------------------------------------- small text helpers
_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


def _number(n):
    return _WORDS[n] if isinstance(n, int) and 0 <= n < len(_WORDS) else str(n)


def _join_or(items):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " or " + items[-1]


def _join_and(items):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _top_genera(predictor, body, limit):
    """The genera most worth naming: the ones with the highest average value among the candidates."""
    groups = {}
    for r in body.candidates:
        value = predictor.species_value(r)
        if value:
            groups.setdefault(r["g"], []).append(value)
    ranked = sorted(groups, key=lambda g: -(sum(groups[g]) / len(groups[g])) * predictor.learned.weight(g))
    return ranked[:limit]
