"""
The systems you own: colonies you claimed with a colonisation ship (journal events ColonisationSystemClaim / ...Release).

Saved in data/owned_systems.json, so she still knows after a restart. When you arrive in one she welcomes you home
(event OwnSystemArrival, her words are in voicepacks/default/colony.json).
"""

from pathlib import Path

from core.logger import get_logger
from journal.exobiology import _read_json, _write_json

log = get_logger("owned_systems")
MAX_SYSTEMS = 500


class OwnedSystems:
    def __init__(self, path=None, on_claim=None):
        self.path = Path(path) if path else None
        self.on_claim = on_claim                   # called with the system name when a NEW claim is noticed (the app uses it for her memory)
        data = _read_json(self.path) if self.path else {}
        self.systems = {k: v for k, v in (data.get("systems") or {}).items() if isinstance(v, dict) and v.get("name")}

    def has(self, name):
        return str(name or "").strip().lower() in self.systems

    def names(self):
        return sorted((v["name"] for v in self.systems.values()), key=str.lower)

    def claim(self, name, address=None, when=""):
        name = str(name or "").strip()
        key = name.lower()
        if not name or key in self.systems or len(self.systems) >= MAX_SYSTEMS:
            return False
        self.systems[key] = {"name": name, "addr": address, "at": str(when or "")}
        self.save()
        if self.on_claim:
            try:
                self.on_claim(name)
            except Exception:
                log.exception("Could not remember the claim")
        return True

    def release(self, name):
        if self.systems.pop(str(name or "").strip().lower(), None) is not None:
            self.save()
            return True
        return False

    def save(self):
        if self.path:
            _write_json(self.path, {"systems": self.systems})
