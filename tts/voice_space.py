"""Disk space for her voice: how much the saved voice lines take, clearing them, and checking there is room for the Australian voice.

Saved lines live in data/voice_cache as small .npy files. They are only a speed-up: any line that is missing is simply made again
(about 1-3 seconds each), so clearing them is always safe. Her memory, settings and recordings are NOT in that folder."""
import shutil
from pathlib import Path

from core import paths


def cache_folder():
    return paths.DATA_DIR / "voice_cache"


def cache_bytes(folder=None):
    folder = Path(folder or cache_folder())
    total = 0
    try:
        for item in folder.glob("*.npy"):
            try:
                total += item.stat().st_size
            except OSError:
                pass
    except OSError:
        pass
    return total


def clear_cache(folder=None):
    """Deletes the saved voice lines only (.npy files). Returns (files deleted, bytes freed)."""
    folder = Path(folder or cache_folder())
    count, freed = 0, 0
    try:
        for item in list(folder.glob("*.npy")):
            try:
                size = item.stat().st_size
                item.unlink()
                count += 1
                freed += size
            except OSError:
                pass
    except OSError:
        pass
    return count, freed


def free_bytes(where=None):
    """Free space on the drive Starling's data lives on (None when it cannot be read)."""
    target = Path(where or paths.DATA_DIR)
    while not target.exists() and target.parent != target:
        target = target.parent
    try:
        return shutil.disk_usage(str(target)).free
    except OSError:
        return None


def gb(number):
    return "%.1f GB" % (number / 1073741824.0)
