"""
Knows where every STARLING folder lives.

Every other file asks THIS file for a folder location,
so nothing else ever has to guess or hard-code a path.
"""

import sys
from pathlib import Path


def _find_root():
    # When STARLING is turned into an .exe (PyInstaller), the project folder
    # is the folder the .exe sits in. Otherwise it is one level above "core".
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


ROOT = _find_root()

CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
DIALOGUE_DIR = ROOT / "dialogue"
VOICEPACKS_DIR = ROOT / "voicepacks"
PLUGINS_DIR = ROOT / "plugins"
LOGS_DIR = ROOT / "logs"
RECORDINGS_DIR = ROOT / "recordings"
DOCS_DIR = ROOT / "docs"

SETTINGS_FILE = CONFIG_DIR / "settings.json"
EVENTS_FILE = CONFIG_DIR / "events.json"
DATABASE_FILE = DATA_DIR / "tetko.db"

# Folders STARLING creates automatically if they are missing.
REQUIRED_FOLDERS = [
    CONFIG_DIR,
    DATA_DIR,
    DIALOGUE_DIR,
    VOICEPACKS_DIR,
    PLUGINS_DIR,
    LOGS_DIR,
]


def ensure_folders():
    """Create any missing folders. Safe to call as many times as you like."""
    for folder in REQUIRED_FOLDERS:
        folder.mkdir(parents=True, exist_ok=True)
