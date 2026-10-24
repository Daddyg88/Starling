"""
Reads YOUR Elite Dangerous key bindings, so "lower the landing gear" presses the key YOU chose.

Elite stores its controls in a plain text (XML) file:
    %LOCALAPPDATA%\\Frontier Developments\\Elite Dangerous\\Options\\Bindings\\Custom.4.0.binds
Each action looks like this:
    <LandingGearToggle>
        <Primary Device="Keyboard" Key="Key_L" />
        <Secondary Device="{NoDevice}" Key="" />
    </LandingGearToggle>
A key combination has <Modifier .../> lines inside Primary/Secondary.

STARLING can only PRESS KEYBOARD keys. If an action is only bound to a joystick button she tells
you, and the fix is to bind a spare keyboard key to it in the game's controls menu as well.

The file is re-read automatically whenever you change your controls in the game.
"""

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from control import keys
from core.logger import get_logger

log = get_logger("binds")

NO_DEVICE = "{nodevice}"

# Why a lookup can fail (the runner turns each into a spoken sentence)
UNBOUND = "unbound"
JOYSTICK_ONLY = "joystick_only"
UNKNOWN_KEY = "unknown_key"
NO_FILE = "no_file"
NOT_IN_FILE = "not_in_file"


@dataclass(frozen=True)
class Keystroke:
    key: str                                  # e.g. "Key_L"
    modifiers: Tuple[str, ...] = ()           # e.g. ("Key_LeftShift",)

    def describe(self):
        return " + ".join(keys.nice_name(k) for k in (*self.modifiers, self.key))


@dataclass
class Slot:
    device: str
    key: str
    modifiers: List[Tuple[str, str]] = field(default_factory=list)   # [(device, key)]

    def is_empty(self):
        return self.device.lower() in ("", NO_DEVICE) or not self.key


@dataclass(frozen=True)
class Match:
    """One Elite action that uses a control (see BindingBook.actions_for)."""
    action: str
    slot: str                                    # "Primary" or "Secondary"
    modifiers: Tuple[Tuple[str, str], ...] = ()  # the shift buttons that go with it
    sure: bool = True                            # False = same button number but the device NAME differs from what we read


def _norm_key(name):
    name = (name or "").strip().lower()
    if name.startswith("key_"):
        name = name[4:]
    return name.replace("_", "").replace("ctrl", "control")


def _alnum(name):
    return "".join(c for c in (name or "").lower() if c.isalnum())


def bindings_folder(environ=None):
    environ = os.environ if environ is None else environ
    base = environ.get("LOCALAPPDATA")
    if not base:
        return None
    return Path(base) / "Frontier Developments" / "Elite Dangerous" / "Options" / "Bindings"


def _preset_names(folder):
    """The preset names written in StartPreset.start (one line per control group, first is the ship)."""
    try:
        text = (Path(folder) / "StartPreset.start").read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def find_binds_file(folder):
    """
    Which .binds file is in use? Returns a Path or None.
    1. the preset named in StartPreset.start (Custom.4.0.binds, Custom.3.0.binds, Custom.binds ...)
    2. otherwise the most recently changed .binds file in the folder
    """
    if folder is None:
        return None
    folder = Path(folder)
    if not folder.is_dir():
        return None
    for name in _preset_names(folder)[:1]:
        exact = [folder / ("%s.%s.binds" % (name, v)) for v in ("4.0", "3.0", "2.0")] + [folder / (name + ".binds")]
        for path in exact:
            if path.is_file():
                return path
        loose = sorted(folder.glob(name + ".*binds"), key=lambda p: p.stat().st_mtime, reverse=True)
        if loose:
            return loose[0]
    everything = sorted(folder.glob("*.binds"), key=lambda p: p.stat().st_mtime, reverse=True)
    return everything[0] if everything else None


def parse_binds(text):
    """XML text -> {"LandingGearToggle": [Slot(primary), Slot(secondary)], ...}. Bad XML raises ValueError."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise ValueError("the binds file is not valid: %s" % error)
    actions = {}
    for element in root:
        slots = []
        for tag in ("Primary", "Secondary"):
            node = element.find(tag)
            if node is None:
                continue
            mods = [(m.get("Device", ""), m.get("Key", "")) for m in node.findall("Modifier")]
            slots.append(Slot(node.get("Device", ""), node.get("Key", ""), mods))
        if slots:
            actions[element.tag] = slots
    return actions


class BindingBook:
    """Knows the player's keys. Re-reads the file when it changes."""

    def __init__(self, folder=None, finder=find_binds_file):
        self.folder = Path(folder) if folder else bindings_folder()
        self._finder = finder
        self._path = None
        self._stamp = None
        self._actions = {}
        self.error = ""

    # ---- loading ----
    def refresh(self):
        """Load (or re-load) the file if it changed. Returns True if bindings are available."""
        path = self._finder(self.folder)
        if path is None:
            self._actions, self._path, self._stamp = {}, None, None
            self.error = "I can't find your Elite Dangerous controls file."
            return False
        try:
            info = path.stat()
        except OSError:
            self.error = "I can't read your controls file."
            return False
        stamp = (str(path), info.st_mtime_ns, info.st_size)
        if stamp == self._stamp:
            return bool(self._actions)
        try:
            self._actions = parse_binds(path.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, ValueError) as error:
            log.error("Could not read %s: %s", path, error)
            self.error = "I couldn't read your controls file."
            return False
        self._path, self._stamp, self.error = path, stamp, ""
        log.info("Loaded %d bindings from %s", len(self._actions), path.name)
        return True

    @property
    def path(self):
        return self._path

    def count(self):
        return len(self._actions)

    # ---- looking up ----
    def lookup(self, action):
        """
        Returns (Keystroke, "") when there is a usable keyboard key,
        or (None, reason) with reason one of UNBOUND, JOYSTICK_ONLY, UNKNOWN_KEY, NO_FILE, NOT_IN_FILE.
        """
        if not self.refresh():
            return None, NO_FILE
        slots = self._actions.get(action)
        if slots is None:
            return None, NOT_IN_FILE
        problem = UNBOUND
        usable = []
        for slot in slots:                       # primary first, then secondary
            if slot.is_empty():
                continue
            if slot.device.lower() != "keyboard" or any(d.lower() != "keyboard" for d, _k in slot.modifiers):
                problem = JOYSTICK_ONLY if problem == UNBOUND else problem
                continue
            names = [slot.key] + [k for _d, k in slot.modifiers]
            if not all(keys.is_known(n) for n in names):
                problem = UNKNOWN_KEY
                log.warning("Unknown key name in the binds file for %s: %s", action, names)
                continue
            usable.append(slot)
        if usable:
            # 0.34.3: when both slots are keyboard keys, prefer the one no other action shares (Enter for UI Select and
            # for the quick comms panel made the launch macro open chat). Otherwise primary first, as before.
            best = next((sl for sl in usable if not self._others_on(action, sl)), usable[0])
            return Keystroke(best.key, tuple(k for _d, k in best.modifiers)), ""
        return None, problem

    def _others_on(self, action, mine_slot):
        """True when another (ship) action uses the same keyboard key and shift keys as this slot."""
        mine = (_norm_key(mine_slot.key), frozenset(_norm_key(m[1]) for m in mine_slot.modifiers))
        for other, slots in self._actions.items():
            if other == action or other.endswith(self.CONTEXT_VARIANTS) or "Humanoid" in other or other.startswith(("Vanity", "FreeCam", "HeadLook")):
                continue
            for slot in slots:
                if slot.is_empty() or slot.device.lower() != "keyboard":
                    continue
                if (_norm_key(slot.key), frozenset(_norm_key(m[1]) for m in slot.modifiers)) == mine:
                    return True
        return False

    CONTEXT_VARIANTS = ("_Buggy", "_Humanoid", "_Fighter", "_MultiCrew")

    def conflicts(self, action):
        """Other ship actions that use the SAME keyboard key (and shift keys) as `action`.

        Elite lets one key do several things. In menus that is fine, but when two actions are live at the same moment
        (for example UI Select and the quick comms panel both on Enter) Elite may do the wrong one, and a macro
        then goes wrong at that key press. Returns a list of action names (SRV / on-foot / fighter versions skipped).
        """
        if not self.refresh():
            return []
        stroke, _why = self.lookup(action)
        if stroke is None:
            return []
        mine = (_norm_key(stroke.key), frozenset(_norm_key(m) for m in stroke.modifiers))
        found = []
        for other, slots in self._actions.items():
            if other == action or other.endswith(self.CONTEXT_VARIANTS) or "Humanoid" in other or other.startswith(("Vanity", "FreeCam", "HeadLook")):
                continue
            for slot in slots:
                if slot.is_empty() or slot.device.lower() != "keyboard":
                    continue
                if (_norm_key(slot.key), frozenset(_norm_key(d_k[1]) for d_k in slot.modifiers)) == mine:
                    found.append(other)
                    break
        return sorted(found)

    def has_action(self, action):
        return action in self._actions

    def slots(self, action):
        """The raw Primary/Secondary slots for an action (empty list if unknown). Used to find joystick fire buttons."""
        self.refresh()
        return list(self._actions.get(action, []))

    def actions_for(self, device, key, held=(), names=()):
        """
        Which Elite actions use this control? (The opposite of lookup: used by the button recorder.)
          device  "Keyboard", or a joystick's id written the way Elite does, like "06A3075C"
          key     "Key_L", "Joy_7", "Joy_POV1Up"
          held    other controls held at the same moment, as [(device, key), ...] (shift buttons)
          names   other names for this joystick, e.g. ["X52 H.O.T.A.S."]. Elite writes some sticks by NAME
                  (Device="SaitekX52") instead of by USB id, so the name is used to recognise them.
        Returns a list of Match, best first: a sure device match before a "same button, device named differently"
        match, a shifted binding before an unshifted one.
        """
        if not self.refresh():
            return []
        wanted_key = _norm_key(key)
        wanted_dev = (device or "").strip().lower()
        keyboard = wanted_dev == "keyboard"
        aliases = [_alnum(n) for n in names if n]

        def canon(dev):
            dev = (dev or "").strip().lower()
            if dev == "keyboard" or dev == wanted_dev:
                return dev
            flat = _alnum(dev)
            for alias in aliases:
                if flat and (flat == alias or flat in alias or alias in flat or ("x52" in flat and "x52" in alias)):
                    return wanted_dev
            return dev

        held_now = {(canon(d), _norm_key(k)) for d, k in held}
        found = []
        for action, slots in self._actions.items():
            for number, slot in enumerate(slots):
                if slot.is_empty() or _norm_key(slot.key) != wanted_key:
                    continue
                slot_dev = canon(slot.device)
                if keyboard != (slot_dev == "keyboard"):
                    continue
                mods = {(canon(d), _norm_key(k)) for d, k in slot.modifiers}
                if mods and not mods <= held_now:
                    continue
                found.append(Match(action, "Primary" if number == 0 else "Secondary", tuple(slot.modifiers),
                                   keyboard or slot_dev == wanted_dev))
        found.sort(key=lambda m: (not m.sure, -len(m.modifiers)))
        return found

    def joystick_names(self):
        """The joystick device names / ids written anywhere in the controls file (shown in recordings)."""
        names = set()
        for slots in self._actions.values():
            for slot in slots:
                for device, _key in [(slot.device, slot.key), *slot.modifiers]:
                    if device and device.lower() not in ("keyboard", NO_DEVICE, "mouse"):
                        names.add(device)
        return sorted(names)
