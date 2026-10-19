"""
Loading and saving settings.json and events.json.

Rules that keep things safe:
  * Missing settings are filled in with defaults.
  * A damaged settings file is backed up (not lost) and defaults are used.
  * Saving is "all or nothing", so a crash mid-save can't wreck the file.
  * Critical (safety) events can NEVER be switched off, even by editing the file.
"""

import copy
import shutil
import json
import os

from core import paths
from core.logger import get_logger

log = get_logger("settings")

DEFAULTS = {
    "app": {"log_level": "INFO", "first_run_done": False, "name": "Starling"},
    "player": {"sex": "neutral"},
    "journal": {"folder": "", "poll_seconds": 1.0},
    "tts": {"provider": "kokoro", "voice": "", "volume": 100, "rate": 0, "pitch": 0, "warm_cache": "idle",
            "clone_reference": "voicepacks/default/clone/Tetko_Issued_Notice.mp3",
            "clone_pack": "custom_covas.pt"},
    "stt": {"enabled": False, "provider": "faster_whisper", "model": "tiny.en", "microphone": "",
            "wake_phrase": "", "require_wake": True, "reply": True, "energy_threshold": 0, "learning": True, "end_silence_ms": 550},
    "facts": {"frequency": "sometimes", "topics": "all"},
    "ask": {"scan_prompts": True, "bio_prompts": True, "answer_seconds": 10},
    "voidcompass": {"enabled": True, "port": 7380},
    "neutron": {"enabled": True, "destination": "", "jump_range": 0, "range_margin": 0.9, "efficiency": 60,
                "supercharge": 4, "clipboard": True, "announce": True, "auto_plot": True, "favourites": {}},
    "bookmarks": {"home": "", "b1": "", "b2": "", "b3": "", "b4": "", "b5": "", "b6": "", "b7": "", "b8": "", "b9": "", "b10": ""},
    "watcher": {"enabled": True, "reply": "often", "wait_for_calm": True},
    "autohonk": {"mode": "off", "hold_seconds": 6.0, "delay_seconds": 2.0},
    "combat_assist": {"pips": True, "heat_sink": True,
                      "pips_delay": 1.2, "fire_buttons": ""},
    "commands": {"enabled": True, "confirm": True, "require_game_focus": True, "disabled": []},
    "smalltalk": {"enabled": True},
    "chitchat": {"enabled": True, "frequency": "normal"},
    "memory": {"enabled": True, "recall_at_login": True},
    "updates": {"repo": "", "auto_check": True, "token": ""},
    "recorder": {"seconds": 20, "countdown": 5},
    "ptt": {"mode": "off", "button": "", "beep": True, "skip_wake": True},
    "personality": {"active_voicepack": "default", "mood": "Friendly", "style": "personality", "mood_mode": "auto", "login_greeting": True, "mood_live": "Friendly",
                    "remarks": "sometimes", "pet_names": True, "innuendo": False, "dark_humour": True, "affection_credits": 500000000},
    "speech": {"enabled": True, "use_recordings": True, "allow_mature": False,
               "windows_emergency_voice": False},
    "ai": {
        "enabled": False,
        "provider": "ollama",
        "model": "",
        "url": "http://localhost:11434",
    },
}


def _merge(defaults, saved):
    """Copy of defaults, with anything in 'saved' laid on top."""
    result = copy.deepcopy(defaults)
    for key, value in saved.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _read_json(path):
    """Read a JSON file. Returns None if it is missing or damaged."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError("top level must be a JSON object")
        return data
    except (ValueError, OSError) as error:
        backup = path.with_name(path.name + ".bad")
        log.error("%s is damaged (%s). Saving a copy as %s", path.name, error, backup.name)
        try:
            os.replace(path, backup)
        except OSError:
            pass
        return None


class Settings:
    def __init__(self, path=None):
        self.path = path or paths.SETTINGS_FILE
        self.values = copy.deepcopy(DEFAULTS)

    def load(self):
        saved = _read_json(self.path)
        self.values = _merge(DEFAULTS, saved) if saved else copy.deepcopy(DEFAULTS)
        return self

    def get(self, dotted_key, default=None):
        """settings.get('tts.volume')"""
        node = self.values
        for part in dotted_key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted_key, value):
        """settings.set('tts.volume', 80)  (call save() afterwards)"""
        parts = dotted_key.split(".")
        node = self.values
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + ".tmp")
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(self.values, handle, indent=2)
        if self.path.exists():
            try:
                shutil.copyfile(self.path, self.path.with_name(self.path.name + ".bak"))   # last good copy
            except OSError:
                pass
        os.replace(temp, self.path)


def load_event_config(path=None):
    """
    Returns {"EventName": {"enabled": bool, "priority": str, "source": str}}.
    Critical events are always forced to enabled.
    """
    path = path or paths.EVENTS_FILE
    raw = _read_json(path) or {}
    events = {}
    for name, info in (raw.get("events") or {}).items():
        if not isinstance(info, dict):
            continue
        priority = info.get("priority", "normal")
        if priority not in ("critical", "normal", "low"):
            priority = "normal"
        enabled = bool(info.get("enabled", True))
        if priority == "critical":
            enabled = True  # safety first: never allow this to be switched off
        events[name] = {
            "enabled": enabled,
            "priority": priority,
            "source": info.get("source", "journal"),
        }
    return events
