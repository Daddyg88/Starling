"""
Loading and saving settings.json and events.json.

Rules that keep things safe:
  * Missing settings are filled in with defaults.
  * A damaged settings file is backed up (not lost) and defaults are used.
  * Saving is "all or nothing", so a crash mid-save can't wreck the file.
  * Critical (safety) events can NEVER be switched off, even by editing the file.
"""

import copy
import difflib
import shutil
import json
import os

from core import paths
from core.logger import get_logger

log = get_logger("settings")

DEFAULTS = {
    "window": {"geometry": "", "maximised": False},
    "app": {"log_level": "INFO", "first_run_done": False, "desktop_shortcut": True, "name": "Starling", "smooth_window": True},
    "player": {"sex": "neutral"},
    "journal": {"folder": "", "poll_seconds": 1.0},
    "tts": {"provider": "kokoro", "voice": "", "volume": 100, "rate": 0, "pitch": 0, "warm_cache": "idle",
            "clone_reference": "voicepacks/default/clone/Tetko_Issued_Notice.mp3",
            "clone_pack": "custom_covas.pt"},
    "stt": {"enabled": False, "provider": "faster_whisper", "model": "base.en", "microphone": "",
            "wake_phrase": "", "require_wake": True, "reply": True, "energy_threshold": 0, "learning": True, "end_silence_ms": 550, "log_everything": False},
    "facts": {"frequency": "sometimes", "topics": "all"},
    "ask": {"scan_prompts": True, "bio_prompts": True, "answer_seconds": 10},
    "plans": {"ask": True},
    "overlay": {"screen": "auto", "bio_enabled": True, "bio_x": 3, "bio_up": 25, "bio_size": "Medium", "bio_dark": False,
                "route_map": "route", "route_size": "Medium", "route_right": 2, "route_top": 10, "route_cockpit_only": True, "route_hide_with_voidcompass": True},
    "streaming": {"enabled": False, "twitch_channel": "", "youtube_key": "", "youtube_video": "", "prefix": "!starling", "who": "everyone", "ask_enabled": True, "announce": True, "recognise_viewers": True, "react": True, "react_milestones": True,
                  "user_cooldown": 45, "action_cooldown": 20, "ask_cooldown": 10, "hold": True, "hold_max": 4, "hold_max_age": 300, "blocked_words": "",
                  "act_lights": True, "act_night_vision": True, "act_head_look": False, "act_scoop": False, "act_gear": False},
    "exobiology": {"distance_alert": True, "distance_beep": True, "guess": True, "top_hint": True, "progress": True},
    "merit": {"power": "", "commodities": ["Platinum", "Osmium", "Painite", "Palladium"]},
    "engineers": {"neutron_over_ly": 1000},
    "dssa": {"neutron_over_ly": 1500},
    "guardian": {"auto_plot_key": True},
    "titans": {"talk": True},
    "materials": {"fill_callout": True, "fill_min_percent": 25},
    "regions": {"announce": True},
    "onfoot": {"auto_shields": False, "preset": "", "auto_health": False, "auto_battery": False, "last_grenade_callout": True},
    "keybinds": {"ship": "", "srv": "", "fighter": "", "multicrew": ""},
    "messages": {"read": True, "npc": False, "channels": "direct"},
    "voidcompass": {"enabled": True, "port": 7380},
    "neutron": {"enabled": True, "destination": "", "jump_range": 0, "range_margin": 0.9, "efficiency": 60,
                "supercharge": 4, "auto_x6": True, "auto_on_target": False, "emergency": True, "clipboard": True, "announce": True, "auto_plot": True, "favourites": {}},
    "nomad": {"stow_hardpoints": True},
    "bookmarks": {"home": "", "b1": "", "b2": "", "b3": "", "b4": "", "b5": "", "b6": "", "b7": "", "b8": "", "b9": "", "b10": "", "fleet": "", "squad": ""},
    "stats": {"enabled": True},
    "binds": {"backup": True},
    "missions": {"reminders": True},
    "watcher": {"attitude": "friends", "enabled": True, "hush": True, "reply": "often", "wait_for_calm": True},
    "autohonk": {"mode": "off", "hold_seconds": 6.0, "delay_seconds": 2.0},
    "combat_assist": {"pips": True, "pips_analysis": True, "heat_sink": True,
                      "pips_delay": 1.2, "pips_delay_analysis": 3.0, "pips_topup_seconds": 8.0, "pips_press_gap": 0.1, "x52_trigger": True, "fire_buttons": ""},
    "commands": {"enabled": True, "confirm": True, "ask_guess": True, "require_game_focus": True, "key_hold": 0.06, "disabled": []},
    "smalltalk": {"enabled": True},
    "brain": {"enabled": True, "knowledge": True, "lookup": False, "freechat": True, "chat_followups": True, "profile": True},
    "llm": {"enabled": False, "model_file": "", "threads": 2, "max_seconds": 8},
    "exploration": {"hge_hint": True},
    "talk": {"combat": True, "exploration": True, "exobiology": True, "mining": True, "trading": True, "antixeno": True},
    "mining": {"prices": True, "merit": True, "limpet_reminder": True, "destination_reminder": True, "chatter": "normal",
               "fav1": "platinum", "fav2": "painite", "fav3": "opal", "fav4": "lowtemperaturediamond", "fav5": "monazite",
               "fav6": "musgravite", "fav7": "serendibite", "fav8": "grandidierite", "fav9": "alexandrite", "fav10": "rhodplumsite"},
    "chitchat": {"enabled": True, "frequency": "normal", "notice": True, "world": True},
    "subtarget": {"press_ahead": False},
    "red_alert": {"minutes": 30, "banner": True, "size": "Medium", "combat_mode": True, "auto_power_plant": True},
    "memory": {"enabled": True, "recall_at_login": True, "habits": True},
    "updates": {"repo": "", "auto_check": True, "ask": False, "ask_reset": False, "token": ""},
    "recorder": {"seconds": 20, "countdown": 5},
    "ptt": {"mode": "off", "button": "", "beep": True, "skip_wake": True},
    "personality": {"active_voicepack": "default", "mood": "Friendly", "style": "personality", "mood_mode": "auto", "login_greeting": True, "mood_live": "Friendly", "mood_level": 3, "mood_level_live": 3,
                    "mood_random": "Friendly", "mood_random_level": 3, "mood_random_minutes": 20, "keep_points": True, "aussie_slang": True,
                    "remarks": "sometimes", "reactions": True, "pet_names": True, "custom_pet_names": "", "innuendo": False, "dark_humour": True, "affection_credits": 500000000},
    "speech": {"enabled": True, "ptt_interrupts": True, "use_recordings": True, "allow_mature": False,
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


_TRUE = {"true", "yes", "on", "1"}
_FALSE = {"false", "no", "off", "0"}


def _fit(value, default):
    """(value to use, problem text or ''). A value of the wrong kind is converted when that is obvious ('40' for a number,
    'yes' for a switch) and otherwise replaced by the default, so one typo in settings.json cannot stop her working."""
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value, ""
        if isinstance(value, str) and value.strip().lower() in _TRUE | _FALSE:
            return value.strip().lower() in _TRUE, "was text, read as a switch"
        return default, "should be true or false"
    if isinstance(default, (int, float)):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value, ""
        if isinstance(value, str):
            try:
                number = float(value.strip())
                return (int(number) if isinstance(default, int) and number == int(number) else number), "was text, read as a number"
            except ValueError:
                pass
        return default, "should be a number"
    if isinstance(default, list) and not isinstance(value, list):
        return default, "should be a list"
    if isinstance(default, dict) and not isinstance(value, dict):
        return default, "should be a group of settings"
    return value, ""


def check_settings(values, defaults, where=""):
    """Walks the loaded settings against the defaults. Returns (checked copy, [plain-words problems]).
    Wrong kinds are fixed as above; keys that are not known (a typo) are kept but reported, with a guess at what was meant."""
    problems, result = [], copy.deepcopy(values)
    for key, default in defaults.items():
        if key not in result:
            continue
        name = where + key
        if isinstance(default, dict) and isinstance(result[key], dict):
            result[key], inner = check_settings(result[key], default, name + ".")
            problems += inner
            continue
        fixed, problem = _fit(result[key], default)
        if problem:
            problems.append("%s %s (it was %r)" % (name, problem, result[key]) if fixed == default else "%s %s" % (name, problem))
        result[key] = fixed
    if where:                                          # inside a known group: spot unknown names
        for key in result:
            if key not in defaults and defaults:
                guess = difflib.get_close_matches(key, list(defaults), n=1, cutoff=0.75)
                if guess:
                    problems.append("%s%s is not a known setting; did you mean %s%s?" % (where, key, where, guess[0]))
    return result, problems


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
        self.problems = []

    def load(self):
        saved = _read_json(self.path)
        self.values = _merge(DEFAULTS, saved) if saved else copy.deepcopy(DEFAULTS)
        if saved:
            self.values, self.problems = check_settings(self.values, DEFAULTS)
            for problem in self.problems:
                log.warning("settings.json: %s", problem)
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
