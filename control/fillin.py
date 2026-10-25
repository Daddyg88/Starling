"""
Helps the PLAYER fill in Elite actions that have NO key at all. It never changes a key you already set.

The safety rules (each one is tested):
  1. Only an action whose Primary AND Secondary are both empty can be filled. Anything with any key or any
     joystick button on it is left completely alone.
  2. Only a key that NOTHING else uses in the same view (ship, on foot, SRV...) is offered, as a key or as a shift key.
  3. Nothing is written until the player picks a key for that action and presses the write button.
  4. A backup copy of the file is made first, next to it (it ends in .starling-backup-<time>, so Elite ignores it).
  5. After the edit the whole file is read again. If ANY other action differs, nothing is written.
  6. Only the one empty Primary line of each chosen action is replaced; the rest of the file stays byte for byte.
"""

import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from control import binds, keys
from core.logger import get_logger

log = get_logger("fillin")

# Plain keys offered, in this order. Elite's own names. Anything Starling cannot press is skipped.
CANDIDATES = (
    [f"Key_Numpad_{i}" for i in range(10)]
    + ["Key_Numpad_Multiply", "Key_Numpad_Subtract", "Key_Numpad_Add", "Key_Numpad_Decimal", "Key_Numpad_Divide"]
    + [f"Key_F{i}" for i in range(1, 13)]
    + ["Key_Insert", "Key_Delete", "Key_Home", "Key_End", "Key_PageUp", "Key_PageDown"]
)
MAX_OFFERED = 8
BACKUP_WORD = ".starling-backup-"


@dataclass
class Gap:
    action: str                 # Elite's name, e.g. HumanoidPing
    label: str                  # what she calls it, e.g. "Ping"
    path: Path                  # the controls file that holds this action
    options: List[str] = field(default_factory=list)      # free keys, Elite names


def _norm(name):
    return (name or "").strip().lower()


def keys_in_use(actions, view):
    """Every keyboard key (and shift key) used by any action in `view`, normalised."""
    used = set()
    for name, slots in actions.items():
        if binds.view_of(name) != view:
            continue
        for slot in slots:
            if slot.is_empty() or slot.device.lower() != "keyboard":
                continue
            used.add(_norm(slot.key))
            used.update(_norm(k) for _d, k in slot.modifiers)
    return used


def free_keys(actions, action, also_taken=()):
    """Keys nothing else uses in this action's view (best first, at most MAX_OFFERED)."""
    taken = keys_in_use(actions, binds.view_of(action)) | {_norm(k) for k in also_taken}
    found = [k for k in CANDIDATES if keys.is_known(k) and _norm(k) not in taken]
    return found[:MAX_OFFERED]


def is_empty_action(slots):
    """True only when there is at least a Primary and every slot has no device and no key (and no chord)."""
    return bool(slots) and all(s.is_empty() and not s.modifiers for s in slots)


def file_for(book, action):
    overlays = getattr(book, "overlays", None) or {}
    return overlays.get(binds.view_of(action)) or book.path


def find_gaps(runner):
    """Actions one of her commands needs that have no key at all. Returns a list of Gap (empty when none)."""
    book = runner.book
    gaps, seen = [], set()
    reported = runner.missing_actions() if hasattr(runner, "missing_actions") else []
    for label, action in reported:
        if action in seen:
            continue
        seen.add(action)
        path = file_for(book, action)
        if path is None:
            continue
        try:
            actions = binds.parse_binds(Path(path).read_text(encoding="utf-8", errors="ignore"))
        except (OSError, ValueError):
            continue
        if not is_empty_action(actions.get(action)):
            continue                                   # has something on it (maybe a joystick): not ours to touch
        options = free_keys(actions, action)
        gaps.append(Gap(action, label, Path(path), options))
    return gaps


def _primary_pattern(action):
    return re.compile(r"(<%s>\s*)<Primary Device=\"\{NoDevice\}\" Key=\"\"\s*/>" % re.escape(action))


def apply_choices(choices, gaps):
    """choices: {action: "Key_Numpad_5"}. Writes only those. Returns (list of sentences about what was done, error text or "").

    Every file is backed up first and checked afterwards; on any doubt nothing is written to it.
    """
    done, errors = [], []
    by_path: Dict[Path, List[Gap]] = {}
    for gap in gaps:
        if choices.get(gap.action):
            by_path.setdefault(gap.path, []).append(gap)
    for path, wanted in by_path.items():
        try:
            raw = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as error:
            errors.append("I could not read %s (%s). Nothing was changed there." % (path.name, error))
            continue
        before = binds.parse_binds(raw)
        text, chosen = raw, {}
        for gap in wanted:
            key = choices[gap.action]
            current = binds.parse_binds(text)
            problem = _why_not(current, gap.action, key, chosen)
            if problem:
                errors.append("%s: %s" % (gap.label, problem))
                continue
            pattern = _primary_pattern(gap.action)
            if len(pattern.findall(text)) != 1:
                errors.append("%s: the file is laid out in a way I do not recognise, so I left it alone." % gap.label)
                continue
            text = pattern.sub(lambda m, k=key: '%s<Primary Device="Keyboard" Key="%s" />' % (m.group(1), k), text, count=1)
            chosen[gap.action] = key
        if not chosen:
            continue
        after = binds.parse_binds(text)
        if not _only_these_changed(before, after, chosen):
            errors.append("%s: the check after the edit failed, so I wrote nothing." % path.name)
            continue
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = path.with_name(path.name + BACKUP_WORD + stamp)
        try:
            shutil.copy2(path, backup)
            temp = path.with_name(path.name + ".starling-temp")
            temp.write_bytes(text.encode("utf-8"))
            os.replace(temp, path)
        except OSError as error:
            errors.append("I could not write %s (%s). Your file is unchanged." % (path.name, error))
            continue
        log.info("Filled %s in %s (backup %s)", chosen, path.name, backup.name)
        for gap in wanted:
            if gap.action in chosen:
                done.append("%s is now %s" % (gap.label, keys.nice_name(chosen[gap.action])))
        done.append("(backup of the old file: %s)" % backup.name)
    return done, " ".join(errors)


def _why_not(actions, action, key, already_chosen):
    slots = actions.get(action)
    if not is_empty_action(slots):
        return "it has a key on it now, so I did not touch it."
    if not keys.is_known(key):
        return "I do not know the key %s." % key
    taken = keys_in_use(actions, binds.view_of(action))
    if _norm(key) in taken:
        return "%s is already used by something else." % keys.nice_name(key)
    if any(_norm(k) == _norm(key) and binds.view_of(a) == binds.view_of(action) for a, k in already_chosen.items()):
        return "you picked %s twice." % keys.nice_name(key)
    return ""


def _only_these_changed(before, after, chosen):
    """True when every action except the chosen ones is identical, and the chosen ones got exactly that one key."""
    if set(before) != set(after):
        return False
    for name, slots in before.items():
        if name in chosen:
            new = after[name]
            if len(new) != len(slots) or new[0].device != "Keyboard" or new[0].key != chosen[name] or new[0].modifiers:
                return False
            if any(a != b for a, b in zip(new[1:], slots[1:])):
                return False
        elif after[name] != slots:
            return False
    return True
