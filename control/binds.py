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


def _resolve_preset(folder, name):
    """The .binds file for a preset name (Custom.4.0.binds, Custom.3.0.binds, Custom.binds ...) or None."""
    exact = [folder / ("%s.%s.binds" % (name, v)) for v in ("4.2", "4.1", "4.0", "3.0", "2.0")] + [folder / (name + ".binds")]
    for path in exact:
        if path.is_file():
            return path
    loose = sorted(folder.glob(name + ".*binds"), key=lambda p: p.stat().st_mtime, reverse=True)
    return loose[0] if loose else None


def humanoid_count(path):
    """How many on-foot actions in this file have a real binding (used to pick the on-foot preset)."""
    try:
        actions = parse_binds(Path(path).read_text(encoding="utf-8", errors="ignore"))
    except (OSError, ValueError):
        return 0
    return sum(1 for name, slots in actions.items() if "Humanoid" in name and any(not sl.is_empty() for sl in slots))


# Names typed on the dashboard's Keybinds page (empty = work it out). Elite lets each group of controls use its own preset.
PRESET_NAMES = {"ship": "", "srv": "", "onfoot": "", "fighter": "", "multicrew": ""}
GROUP_LABELS = {"ship": "Ship", "srv": "SRV", "onfoot": "On foot", "fighter": "Ship-launched fighter", "multicrew": "Multicrew"}


def set_preset_names(settings):
    """Copy the names from the settings (keybinds.ship, keybinds.srv, onfoot.preset, ...) into PRESET_NAMES."""
    for group, key in (("ship", "keybinds.ship"), ("srv", "keybinds.srv"), ("onfoot", "onfoot.preset"),
                       ("fighter", "keybinds.fighter"), ("multicrew", "keybinds.multicrew")):
        PRESET_NAMES[group] = str(settings.get(key, "") or "").strip()


def _candidate_foot_files(folder, ship_path):
    """Other controls files that might hold the on-foot keys, best guess first."""
    out, seen = [], set()

    def add(path):
        if path is not None and path != ship_path and path not in seen:
            seen.add(path)
            out.append(path)
    if PRESET_NAMES["onfoot"].strip():                            # 1. the name you typed
        add(_resolve_preset(folder, PRESET_NAMES["onfoot"].strip()))
        if out:
            return out
    for name in _preset_names(folder):                            # 2. the other presets StartPreset.start names
        add(_resolve_preset(folder, name))
    if out:
        return out
    try:                                                          # 3. any other controls file, newest first
        others = sorted((p for p in folder.glob("*.binds") if p != ship_path), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        others = []
    for path in others:
        add(path)
    return out


def find_foot_binds_file(folder, ship_path=None):
    """
    Elite lets the ship, SRV and on-foot controls each use a DIFFERENT preset (your on-foot page says MCUSTOM, the ship uses
    HCS Custom). Returns the .binds file that holds the on-foot keys when it is not the ship's file, otherwise None.
    Which one is the on-foot preset is not written down anywhere reliable, so: the name you typed on the On foot page, else
    the other presets named in StartPreset.start, else any other controls file in the folder. Of those, the one with the
    most on-foot keys set wins (a file with fewer than 10 is ignored).
    """
    if folder is None:
        return None
    folder = Path(folder)
    if not folder.is_dir():
        return None
    best, best_count = None, 9
    for path in _candidate_foot_files(folder, ship_path):
        count = humanoid_count(path)
        if count > best_count:
            best, best_count = path, count
    return best


def describe_folder(folder):
    """A few plain lines for the key check: what StartPreset.start says and which controls files exist."""
    if folder is None or not Path(folder).is_dir():
        return ["The Elite controls folder was not found."]
    folder = Path(folder)
    lines = ["StartPreset.start names: %s" % (", ".join(_preset_names(folder)) or "(nothing / file missing)")]
    try:
        for path in sorted(folder.glob("*.binds"), key=lambda p: p.stat().st_mtime, reverse=True)[:8]:
            import time as _t
            lines.append("  %s - saved %s - %d on-foot keys set" % (
                path.name, _t.strftime("%d %b %H:%M", _t.localtime(path.stat().st_mtime)), humanoid_count(path)))
    except OSError:
        pass
    return lines


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
    typed = PRESET_NAMES["ship"].strip()
    if typed:
        found = _resolve_preset(folder, typed)
        if found is not None:
            return found
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


def view_of(action):
    """Which Elite 'view' an action works in. Two actions can only get in each other's way if they share a view.

    ship = flying, targeting, the cockpit panels and menus (all live together); galaxymap, fss (system scanner),
    saa (surface scanner), camera, srv, onfoot, fighter and multicrew are separate screens or vehicles.
    """
    name = action or ""
    if "Humanoid" in name:
        return "onfoot"
    if name.endswith("_Buggy") or name.startswith("Buggy"):
        return "srv"
    if name.endswith("_Fighter") or name.startswith(("Fighter", "Order")):
        return "fighter"
    if name.endswith("_MultiCrew") or name.startswith("MultiCrew"):
        return "multicrew"
    if name.startswith("ExplorationFSS"):
        return "fss"
    if name.startswith("ExplorationSAA"):
        return "saa"
    if name.startswith("GalaxyMap") and name != "GalaxyMapOpen":
        return "galaxymap"
    if name.startswith(("FreeCam", "Vanity", "MoveFreeCam", "Photo")):
        return "camera"
    return "ship"


class BindingBook:
    """Knows the player's keys. Re-reads the file when it changes."""

    def __init__(self, folder=None, finder=find_binds_file, foot_finder=find_foot_binds_file):
        self.folder = Path(folder) if folder else bindings_folder()
        self._finder = finder
        self._foot_finder = foot_finder
        self._overlays = {}
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
        try:
            foot = self._foot_finder(self.folder, path) if self._foot_finder else None
            foot_info = foot.stat() if foot is not None else None
        except OSError:
            foot, foot_info = None, None
        overlays = {}                                  # group -> file that holds that group's keys
        try:
            foot = self._foot_finder(self.folder, path) if self._foot_finder else None
            if foot is not None:
                overlays["onfoot"] = foot
            for group in ("srv", "fighter", "multicrew"):                     # only when you typed a name for it
                typed = PRESET_NAMES[group].strip()
                other = _resolve_preset(Path(self.folder), typed) if typed and self.folder else None
                if other is not None and other != path:
                    overlays[group] = other
            infos = {g: p.stat() for g, p in overlays.items()}
        except OSError:
            overlays, infos = {}, {}
        stamp = (str(path), info.st_mtime_ns, info.st_size,
                 tuple(sorted((g, str(p), infos[g].st_mtime_ns, infos[g].st_size) for g, p in overlays.items())))
        if stamp == self._stamp:
            return bool(self._actions)
        try:
            self._actions = parse_binds(path.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, ValueError) as error:
            log.error("Could not read %s: %s", path, error)
            self.error = "I couldn't read your controls file."
            return False
        self._overlays = {}
        for group, other in overlays.items():
            try:
                theirs = parse_binds(other.read_text(encoding="utf-8", errors="ignore"))
            except (OSError, ValueError) as error:
                log.warning("Could not read the %s controls %s: %s", group, other, error)
                continue
            taken = 0
            for name, slots in theirs.items():
                if view_of(name) == group:
                    self._actions[name] = slots
                    taken += 1
            self._overlays[group] = other
            log.info("%s keys (%d) come from %s, the rest from %s", GROUP_LABELS[group], taken, other.name, path.name)
        self._path, self._stamp, self.error = path, stamp, ""
        log.info("Loaded %d bindings from %s", len(self._actions), path.name)
        return True

    @property
    def overlays(self):
        """{"onfoot": Path, ...}: the groups whose keys are read from a different file than the ship's."""
        return dict(self._overlays)

    @property
    def foot_path(self):
        """The separate file the on-foot keys come from, or None when they are in the main file."""
        return self._overlays.get("onfoot")

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
            if other == action or view_of(other) != view_of(action):
                continue                       # a different screen or vehicle: the two never meet
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
        then goes wrong at that key press. Returns a list of action names (only actions in the same view count: see view_of).
        """
        if not self.refresh():
            return []
        stroke, _why = self.lookup(action)
        if stroke is None:
            return []
        mine = (_norm_key(stroke.key), frozenset(_norm_key(m) for m in stroke.modifiers))
        found = []
        for other, slots in self._actions.items():
            if other == action or view_of(other) != view_of(action):
                continue                       # a different screen or vehicle: the two never meet
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
