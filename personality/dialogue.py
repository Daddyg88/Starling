"""
Dialogue: everything STARLING can say, loaded from JSON files.

Nothing she says is written in the program itself. Lines live in:
  voicepacks/<pack>/dialogue.json    recorded lines (text plus an mp3)
  dialogue/core_lines.json           text-only back-up lines

A "key" is an event name such as "FuelScoop". A mood variation adds a suffix:
"FuelScoop_Sarcastic". A line can be:
    "Just text"
or  {"text": "...", "audio": "file.mp3", "mature": false, "then_speak": false,
         "after_text": "...", "planned": false}
  text        what she says (also the back-up if the mp3 is missing)
  after_text  spoken with the Windows voice AFTER the recording, e.g. "{Species_Localised}"
  planned     true = "I will record this later"; spoken as text until the mp3 appears
"""

import json
import os
import random
import re
import tempfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.logger import get_logger
from personality import moods

log = get_logger("dialogue")


@dataclass(frozen=True)
class Line:
    key: str
    text: str
    audio: Optional[str] = None
    mature: bool = False
    then_speak: bool = False
    after_text: str = ""     # spoken with the Windows voice after the recording
    planned: bool = False    # a recording you intend to make: spoken as text until then


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        log.error("Could not read %s: %s", path, error)
        return {}


def _make_line(key, raw):
    if isinstance(raw, str):
        return Line(key=key, text=raw)
    if isinstance(raw, dict) and (raw.get("text") or raw.get("audio")):
        return Line(
            key=key,
            text=str(raw.get("text") or ""),
            audio=raw.get("audio") or None,
            mature=bool(raw.get("mature", False)),
            then_speak=bool(raw.get("then_speak", False)),
            after_text=str(raw.get("after_text") or ""),
            planned=bool(raw.get("planned", False)),
        )
    return None


GLOBAL_MEMORY = 40          # how many recent lines (of any kind) she avoids repeating
OPENER_MEMORY = 5           # ...and how many recent openings ('Right now we're', 'Nice work') she tries not to start with again
SAVE_EVERY = 25             # picks between saves of her 'what I said lately' memory


def opener_of(text):
    """The first two words, lower case: 'Nice work on that one.' -> 'nice work'."""
    words = re.findall(r"[a-z']+", str(text).lower())
    return " ".join(words[:2])


class DialogueManager:
    def __init__(self, pack_dir=None, extra_files=(), rng=None):
        self.pack_dir = Path(pack_dir) if pack_dir else None
        self.extra_files = [Path(p) for p in extra_files]
        self.rng = rng or random.Random()
        self.lines = {}
        self.pack_info = {}
        self._recent = {}                                # key -> the last few line texts used for it
        self._spoken = deque(maxlen=GLOBAL_MEMORY)       # the last lines picked for ANY key, so similar lines do not follow each other
        self._memory_file = None
        self._since_save = 0
        self._audio_exists = {}

    # ---- remembering what she said lately (kept between starts, so a new session does not open with the same lines) ----
    def attach_memory(self, path):
        self._memory_file = Path(path)
        try:
            data = json.loads(self._memory_file.read_text(encoding="utf-8"))
            for key, texts in (data.get("recent") or {}).items():
                self._recent[str(key)] = deque((str(t) for t in texts), maxlen=max(3, len(texts)))
            self._spoken.extend(str(t) for t in (data.get("spoken") or [])[-GLOBAL_MEMORY:])
        except (OSError, ValueError, AttributeError):
            pass
        return self

    def save_memory(self):
        if self._memory_file is None:
            return
        self._since_save = 0
        data = {"recent": {key: list(texts)[-40:] for key, texts in self._recent.items() if texts}, "spoken": list(self._spoken)}
        try:
            self._memory_file.parent.mkdir(parents=True, exist_ok=True)
            handle, temp = tempfile.mkstemp(dir=str(self._memory_file.parent), suffix=".tmp")
            with os.fdopen(handle, "w", encoding="utf-8") as out:
                json.dump(data, out)
            os.replace(temp, self._memory_file)
        except OSError:
            log.warning("Could not save what she said lately", exc_info=True)

    # ---- loading ----
    def load(self):
        self.lines = {}
        if self.pack_dir is not None and self.pack_dir.is_dir():
            self.pack_info = _read_json(self.pack_dir / "pack.json")
            dialogue_file = self.pack_info.get("dialogue_file", "dialogue.json")
            self._merge(_read_json(self.pack_dir / dialogue_file))
            self._merge(_read_json(self.pack_dir / "personality.json"))   # remarks, pet names, extra moods
            self._merge(_read_json(self.pack_dir / "commands.json"))      # what she says about voice commands
            self._merge(_read_json(self.pack_dir / "ask.json"))           # her questions and replies to your answers
            self._merge(_read_json(self.pack_dir / "facts.json"))         # the "I've been reading" facts
            self._merge(_read_json(self.pack_dir / "travel.json"))        # more arrival / departure lines
            self._merge(_read_json(self.pack_dir / "innuendo.json"))      # the cheeky lines (only with the dashboard switch on)
            self._merge(_read_json(self.pack_dir / "aussie.json"))        # Australian slang (only with the Australian voice)
            self._merge(_read_json(self.pack_dir / "hack.json"))          # the base-mapping game
            self._merge(_read_json(self.pack_dir / "hack_lore.json"))     # her story, one chapter per base
            self._merge(_read_json(self.pack_dir / "dark.json"))          # gallows humour
            self._merge(_read_json(self.pack_dir / "route.json"))         # neutron route plotter
            self._merge(_read_json(self.pack_dir / "watcher.json"))       # her answers to the Watcher (Void Compass)
            self._merge(_read_json(self.pack_dir / "manners.json"))       # "you're welcome"
            self._merge(_read_json(self.pack_dir / "talk.json"))          # longer, chattier versions of everyday lines
            self._merge(_read_json(self.pack_dir / "lore.json"))          # her back story (East Orion Company)
            self._merge(_read_json(self.pack_dir / "smalltalk.json"))     # answers when you chat to her
            self._merge(_read_json(self.pack_dir / "brain.json"))         # her "brain": opinions, game answers, streaming, riddles
            self._merge(_read_json(self.pack_dir / "confirm.json"))       # "did you mean...?" when she is nearly sure
            self._merge(_read_json(self.pack_dir / "more.json"))          # extra lines for the call-outs she says most
            self._merge(_read_json(self.pack_dir / "chat2.json"))         # opinion about "it", greetings
            self._merge(_read_json(self.pack_dir / "state_talk.json"))    # remarks about the hull, a bounty, a long session
            self._merge(_read_json(self.pack_dir / "rings.json"))         # ring hotspots
            self._merge(_read_json(self.pack_dir / "profile.json"))       # what she learns about you, and says she has learned
            self._merge(_read_json(self.pack_dir / "freechat.json"))      # free chat: reactions, remarks and questions back
            self._merge(_read_json(self.pack_dir / "brain2.json"))        # "say that again", "what were we talking about"
            self._merge(_read_json(self.pack_dir / "chitchat.json"))      # small talk when it is quiet
            self._merge(_read_json(self.pack_dir / "openers.json"))        # tiny reactions before an ordinary line (Hm. / Oh. / Again.)
            self._merge(_read_json(self.pack_dir / "combat.json"))        # ship changes, wings, fighting (space and on foot)
            self._merge(_read_json(self.pack_dir / "memory.json"))        # what she remembers about you
            self._merge(_read_json(self.pack_dir / "eoc.json"))           # the East Orion Company: CEO, systems, tour
            self._merge(_read_json(self.pack_dir / "shopping.json"))      # she loves shopping (new ships, modules, stations)
            self._merge(_read_json(self.pack_dir / "mining.json"))        # mining callouts and price answers
            self._merge(_read_json(self.pack_dir / "mining2.json"))       # more mining lines (less repetition)
            self._merge(_read_json(self.pack_dir / "plans.json"))         # "What are we doing today?"
            self._merge(_read_json(self.pack_dir / "selling.json"))       # where to sell: options A and B, plot a route?
            self._merge(_read_json(self.pack_dir / "jumps.json"))         # many more jump lines, plain and dry as well as warm
            self._merge(_read_json(self.pack_dir / "ships.json"))         # ship comments, favourite ship, welcome home
            self._merge(_read_json(self.pack_dir / "callouts.json"))      # glide, scoopable star, undiscovered system, jumps left
            self._merge(_read_json(self.pack_dir / "exobiology.json"))    # guesses what lives on a planet and what it is worth
            self._merge(_read_json(self.pack_dir / "training.json"))      # the voice training session
            self._merge(_read_json(self.pack_dir / "variety.json"))       # long-session variety: jet cone boosts, neutron and white dwarf jumps
            self._merge(_read_json(self.pack_dir / "progress.json"))      # milestones, codex progress, the one-of-a-kind species
            self._merge(_read_json(self.pack_dir / "planets.json"))       # green gas giants, gas giants with life, rare giants
            self._merge(_read_json(self.pack_dir / "dssa.json"))          # "plot me a route to the nearest DSSA"
            self._merge(_read_json(self.pack_dir / "colony.json"))        # welcome home to systems you own
            self._merge(_read_json(self.pack_dir / "nsp.json"))           # notable stellar phenomena (Lagrange clouds, molluscs, crystals...)
            self._merge(_read_json(self.pack_dir / "materials.json"))     # "you are 82 percent full on iron"
            self._merge(_read_json(self.pack_dir / "titans.json"))        # Thargoid Titans: routes, war story, how each one fell
            self._merge(_read_json(self.pack_dir / "guardian.json"))      # guardian blueprint sites and spoken guides
            self._merge(_read_json(self.pack_dir / "engineers.json"))     # "take me to Felicity Farseer"
            self._merge(_read_json(self.pack_dir / "merit.json"))         # "I want to go merit mining"
            self._merge(_read_json(self.pack_dir / "missions.json"))       # mission expiry and hand-in reminders
            self._merge(_read_json(self.pack_dir / "stats.json"))          # "how many kills / jumps / visits"
            self._merge(_read_json(self.pack_dir / "services.json"))      # "where is the nearest material trader / black market"
            self._merge(_read_json(self.pack_dir / "biodistance.json"))   # beep + "far enough, take the next sample"
            self._merge(_read_json(self.pack_dir / "regions.json"))       # entering a galaxy region, first time in a region
            self._merge(_read_json(self.pack_dir / "messages.json"))      # incoming chat read aloud
            self._merge(_read_json(self.pack_dir / "streaming.json"))     # chat questions and chat actions (Twitch / YouTube)
            self._merge(_read_json(self.pack_dir / "routemap.json"))      # "hide the route map" / "show the route map"
            self._merge(_read_json(self.pack_dir / "carriers.json"))      # routes to the fleet carrier and the squad carrier
            self._merge(_read_json(self.pack_dir / "launch.json"))        # "I have control", "checking systems", launch speech
            self._merge(_read_json(self.pack_dir / "moods.json"))         # lines for Infatuated and Upset
            self._merge(_read_json(self.pack_dir / "tone.json"))          # mood + level asides (Tone_<Mood>_L1..L5)
            self._merge(_read_json(self.pack_dir / "neutral.json"))       # more personality for Neutral
            self._merge(_read_json(self.pack_dir / "onfoot.json"))        # medpack, energy cell, last grenade (on foot care)
            self._merge(_read_json(self.pack_dir / "swings.json"))        # mood swings: forgiving you, data lost, rebuy, trade loss
            self._merge(_read_json(self.pack_dir / "showoff.json"))       # "show off": she talks while she opens the maps and panels
            self._merge(_read_json(self.pack_dir / "bio.json"))           # biology: value on the first sample, what it is on the second
            self._merge(_read_json(self.pack_dir / "jealous.json"))         # jealous of other AIs and other games; she is the best
            self._merge(_read_json(self.pack_dir / "dockjokes.json"))     # funny lines when you are back aboard from the Nomad or the SRV
        elif self.pack_dir is not None:
            log.warning("Voice pack folder not found: %s", self.pack_dir)
        for path in self.extra_files:
            self._merge(_read_json(path))
        count = sum(len(v) for v in self.lines.values())
        log.info("Dialogue loaded: %d lines under %d keys", count, len(self.lines))
        return self

    def _merge(self, data):
        for key, raw_lines in data.items():
            if key.startswith("_") or not isinstance(raw_lines, list):
                continue
            for raw in raw_lines:
                line = _make_line(key, raw)
                if line is not None:
                    self.lines.setdefault(key, []).append(line)

    # ---- audio files ----
    def audio_path(self, line):
        """Full path of the line's mp3, or None if it has none or the file is missing."""
        if not line.audio or self.pack_dir is None:
            return None
        folder = self.pack_info.get("audio_folder", "audio")
        path = self.pack_dir / folder / line.audio
        if path not in self._audio_exists:
            self._audio_exists[path] = path.is_file()
        return path if self._audio_exists[path] else None

    def missing_audio(self):
        """Lines that name an mp3 that is not in the audio folder (a real problem)."""
        return [(k, l.audio) for k, ls in self.lines.items() for l in ls
                if l.audio and not l.planned and self.audio_path(l) is None]

    def waiting_for_recording(self):
        """Planned lines whose mp3 you have not added yet (spoken as text for now)."""
        return [(k, l.audio) for k, ls in self.lines.items() for l in ls
                if l.audio and l.planned and self.audio_path(l) is None]

    # ---- choosing a line ----
    def pool(self, key, mood="", allow_mature=False, prefer_recorded=True):
        """All lines that could be used for this key and mood."""
        found = list(self.lines.get(key, []))
        if mood:
            found += self.lines.get("%s_%s" % (key, mood), [])
            parent = moods.PARENT.get(mood)                      # Infatuated also uses Close lines, Upset also Frustrated lines
            if parent:
                found += self.lines.get("%s_%s" % (key, parent), [])
        if not allow_mature:
            found = [line for line in found if not line.mature]
        if prefer_recorded:
            recorded = [line for line in found if self.audio_path(line) is not None]
            if recorded:
                found = recorded
        return found

    def pick(self, key, mood="", allow_mature=False, prefer_recorded=True):
        """Choose one line, avoiding the ones used most recently. None if there are none."""
        found = self.pool(key, mood, allow_mature, prefer_recorded)
        if not found:
            return None
        size = max(3, min(60, int(len(found) * 0.75)))        # big pools remember more (three quarters of the pool), so a line is not heard again soon
        if len(found) <= 12:
            size = max(size, len(found) - 1)                  # a small pool uses every line before any is heard twice
        recent = self._recent.get(key)
        if recent is None or recent.maxlen != size:
            recent = self._recent[key] = deque(recent or (), maxlen=size)
        fresh = [line for line in found if line.text not in recent] or found
        lately = set(self._spoken)                                   # not a line she said a moment ago under another key either
        fresher = [line for line in fresh if line.text not in lately] or fresh
        openers = {opener_of(text) for text in list(self._spoken)[-OPENER_MEMORY:]}
        varied = [line for line in fresher if opener_of(line.text) not in openers] or fresher
        choice = self.rng.choice(varied)
        recent.append(choice.text)
        self._spoken.append(choice.text)
        self._since_save += 1
        if self._memory_file is not None and self._since_save >= SAVE_EVERY:
            self.save_memory()
        return choice
