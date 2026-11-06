"""Safety copies of her saved data, and the version stamp that lets later versions upgrade old files.

* backup_if_new_version(): the first time a NEW version starts, copy data/ (without the big voice and model caches) into
  data_backups/<old version>-<date>/ and keep only the newest few.
* run_migrations(): runs any upgrade steps that are newer than the data's stamp (data/data_format.json). There are none yet:
  add one to MIGRATIONS when a saved file changes shape, and a tester's old file is upgraded instead of breaking.
"""
import json
import shutil
from datetime import datetime
from pathlib import Path

from core.logger import get_logger

log = get_logger("backup")

KEEP_BACKUPS = 3
SKIP = {"voice_cache", "llm", "poi_cache.json", "cache"}        # big and re-makeable
STAMP = "data_format.json"
FORMAT = 1                                                      # raise by one for each new upgrade step below

MIGRATIONS = []          # [(format_number, function(data_dir))], each one makes the data fit that format


def _stamp(data_dir):
    try:
        return json.loads((Path(data_dir) / STAMP).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_stamp(data_dir, stamp):
    try:
        (Path(data_dir) / STAMP).write_text(json.dumps(stamp), encoding="utf-8")
    except OSError:
        log.warning("Could not write the data version note", exc_info=True)


def backup_if_new_version(data_dir, backups_dir, version, now=None):
    """Returns the backup folder made, or None (first ever start, same version, or nothing to copy)."""
    data, backups = Path(data_dir), Path(backups_dir)
    stamp = _stamp(data)
    old = stamp.get("version")
    if old == version:
        return None
    made = None
    if old is not None and data.is_dir():                       # an upgrade: keep what the old version had
        stamp_day = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
        made = backups / ("%s-%s" % (old, stamp_day))
        try:
            made.mkdir(parents=True, exist_ok=True)
            for item in data.iterdir():
                if item.name in SKIP:
                    continue
                if item.is_dir():
                    shutil.copytree(item, made / item.name, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, made / item.name)
            log.info("Saved a copy of her data from version %s in %s", old, made)
        except OSError:
            log.warning("Could not make the data backup", exc_info=True)
            made = None
        _prune(backups)
    stamp["version"] = version
    _write_stamp(data, stamp)
    return made


def _prune(backups):
    try:
        folders = sorted((p for p in Path(backups).iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return
    for old in folders[KEEP_BACKUPS:]:
        shutil.rmtree(old, ignore_errors=True)


def run_migrations(data_dir, migrations=None, current=None):
    """Runs the upgrade steps the data has not had yet, in order. Returns how many ran. A failing step is logged and stops the rest
    (the data stays at its old format and is tried again at the next start)."""
    steps = sorted(MIGRATIONS if migrations is None else migrations, key=lambda item: item[0])
    target = FORMAT if current is None else current
    stamp = _stamp(data_dir)
    have = int(stamp.get("format", 0) or 0)
    ran = 0
    for number, step in steps:
        if number <= have or number > target:
            continue
        try:
            step(Path(data_dir))
        except Exception:
            log.exception("Data upgrade %s failed; her data stays at format %s", number, have)
            if have != int(stamp.get("format", 0) or 0):
                stamp["format"] = have
                _write_stamp(data_dir, stamp)
            return ran
        have = number
        ran += 1
        log.info("Upgraded her data to format %s", number)
    if int(stamp.get("format", 0) or 0) != max(have, target):
        stamp["format"] = max(have, target)
        _write_stamp(data_dir, stamp)
    return ran
