"""Finds the folder where Elite Dangerous writes its journal files."""

import os
import sys
from pathlib import Path

from core.logger import get_logger

log = get_logger("locator")

_SAVED_GAMES_ID = "{4C5C32FF-BB9D-43B0-B5B4-2D72E54EAAA4}"
_GAME_SUBFOLDER = Path("Frontier Developments") / "Elite Dangerous"


def _saved_games_from_registry():
    """Windows remembers where 'Saved Games' really is (it may have been moved)."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        )
        value, _kind = winreg.QueryValueEx(key, _SAVED_GAMES_ID)
        winreg.CloseKey(key)
        return Path(os.path.expandvars(value))
    except OSError:
        return None


def candidate_folders(configured=""):
    """Every place the journal might be, best guess first."""
    found = []
    if configured:
        found.append(Path(configured).expanduser())
    saved = _saved_games_from_registry()
    if saved:
        found.append(saved / _GAME_SUBFOLDER)
    found.append(Path.home() / "Saved Games" / _GAME_SUBFOLDER)
    for variable in ("OneDrive", "OneDriveConsumer"):
        base = os.environ.get(variable)
        if base:
            found.append(Path(base) / "Saved Games" / _GAME_SUBFOLDER)
    return found


def find_journal_folder(configured=""):
    """Returns the journal folder as a Path, or None if it can't be found."""
    for folder in candidate_folders(configured):
        if folder.is_dir():
            log.info("Journal folder: %s", folder)
            return folder
    log.warning("Could not find the Elite Dangerous journal folder.")
    return None
