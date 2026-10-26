"""
GUARDIAN BLUEPRINT SITES: "plot me a route to the guardian weapon blueprint", "how do I get the guardian module blueprints".

The sites are in config/guardian.json. The vessel (and fighter) blueprints take two stops: the beacon first (to collect an Ancient Key),
then the structure (to use it). She waits for the key to arrive in your cargo, then tells you the next stop and plots it.
Her spoken guides are in voicepacks/default/guardian.json (one line per step, said in order).
The actual plotting (galaxy map macro for close sites, a Spansh neutron route past 1000 light years) is done by RouteVoice.
"""

import json
import re

from core import paths
from core.logger import get_logger

log = get_logger("guardian")

_ABOUT = re.compile(r"\bguardian\b.*\b(blue ?prints?|blueprint)\b|\b(blue ?prints?)\b.*\bguardian\b")
_HOW = re.compile(r"\b(how (do|can|would|should|to|does)|tell me how|explain|walk me through|guide|instructions?|what do i do)\b")
_GO = re.compile(r"\b(plot|set|take|bring|fly|get|navigate|head|go|route|course|lead|find|send)\b")
_WHERE = re.compile(r"\bwhere\b")
_ALT = re.compile(r"\b(alternative|alternate|other|classic|different|another)\b")
_KINDS = (("vessel", re.compile(r"\b(vessels?|fighters?|ships?)\b")),
          ("weapon", re.compile(r"\b(weapons?|guns?)\b")),
          ("module", re.compile(r"\b(modules?|mod)\b")))
KEY = "ancientkey"


def load(path=None):
    path = path or (paths.CONFIG_DIR / "guardian.json")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        log.exception("Could not read %s", path)
        return {}
    return {k: v for k, v in raw.items() if isinstance(v, dict)}


def parse(said):
    """What was asked: None, or (kind, intent) with kind module/weapon/vessel and intent 'guide', 'go' or 'where'.
    `said` is already lower case with the punctuation removed (navigation.voice.clean)."""
    if not _ABOUT.search(said):
        return None
    kind = next((name for name, pattern in _KINDS if pattern.search(said)), None)
    if kind is None:
        return None
    if _HOW.search(said):
        return kind, "guide"
    if _GO.search(said):
        return kind, "go"
    if _WHERE.search(said):
        return kind, "where"
    return kind, "go"


def wants_alternative(said):
    return bool(_ALT.search(said))


def is_key(cargo_type):
    """True for the Ancient Key (journal cargo name 'ancientkey')."""
    return KEY in re.sub(r"[^a-z]", "", str(cargo_type or "").lower())
