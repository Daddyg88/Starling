"""
Button recorder: watches every key, mouse side button, joystick button and hat you press for a few seconds,
with exact timing, and writes a report you can send for help building macros.

It also writes down what the GAME was doing at the time (which screen was open, which switches changed, which
journal events arrived), so "press this button, wait for DockingGranted, press that one" can be seen clearly.

It presses NOTHING. It only watches.

How it works
  * about 60 times a second it asks Windows which controls are held down (same calls the push-to-talk button uses)
  * a change from "up" to "down" is recorded as a press, "down" to "up" as a release (with how long it was held)
  * every press is looked up in YOUR Elite controls file to find the action it triggers (UI_Select, ...)
  * the report ends with a suggested macro in the format Starling's settings.json uses

LIMITS (said plainly)
  * Windows only reports the first 32 buttons and ONE hat per joystick, and no axes (stick movement, sliders).
    X52 "mode" shifted buttons usually do not show up as separate buttons here.
  * The suggested macro is a starting point. Starling can only press KEYBOARD keys, so an action with no
    keyboard key bound in Elite is flagged: bind a spare key to it in the game and it will work.
"""

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from control.inputs import VK_NAME, MOUSE_NAME, hat_directions, hat_spec, joy_spec, key_spec, mouse_spec
from core.logger import get_logger
from events.status_flags import FLAGS2_NAMES, FLAGS_NAMES, SCREENS

log = get_logger("recorder")

POLL_SECONDS = 0.015            # how often the buttons are read
CONTEXT_SECONDS = 0.25          # how often Status.json / the journal are read
HOLD_MIN = 0.4                  # a press this long or longer becomes a "hold" step
WAIT_MIN = 0.15                 # gaps shorter than this are left out of the macro
WAIT_STEP = 0.05
WAIT_MAX = 5.0
REPEAT_GAP = 0.4                # the same button pressed again within this time becomes "xN"
QUIET_JOURNAL = {"Music"}       # journal events that are only noise here

# Windows key name (control/inputs.py VK) -> the name Elite uses in its controls file
_ELITE_NAMES = {
    "Left": "Key_LeftArrow", "Right": "Key_RightArrow", "Up": "Key_UpArrow", "Down": "Key_DownArrow",
    "LeftCtrl": "Key_LeftControl", "RightCtrl": "Key_RightControl", "LeftShift": "Key_LeftShift",
    "RightShift": "Key_RightShift", "LeftAlt": "Key_LeftAlt", "RightAlt": "Key_RightAlt",
    "Semicolon": "Key_SemiColon", "Quote": "Key_Apostrophe", "Backslash": "Key_BackSlash",
    "NumpadMultiply": "Key_Numpad_Multiply", "NumpadAdd": "Key_Numpad_Add", "NumpadSubtract": "Key_Numpad_Subtract",
    "NumpadDecimal": "Key_Numpad_Decimal", "NumpadDivide": "Key_Numpad_Divide",
}
KEYBOARD_MODIFIERS = {"LeftCtrl", "RightCtrl", "LeftShift", "RightShift", "LeftAlt", "RightAlt"}


def elite_control(spec):
    """'joy:06A3:075C:7' -> ('06A3075C', 'Joy_7'); 'key:F5' -> ('Keyboard', 'Key_F5'); None if Elite has no name for it."""
    kind, _, rest = (spec or "").partition(":")
    if kind == "key":
        if rest in _ELITE_NAMES:
            return "Keyboard", _ELITE_NAMES[rest]
        if rest.startswith("Numpad") and rest[6:].isdigit():
            return "Keyboard", "Key_Numpad_" + rest[6:]
        return "Keyboard", "Key_" + rest
    if kind == "joy":
        try:
            vendor, product, button = rest.split(":")
            return vendor.upper() + product.upper(), "Joy_%d" % int(button)
        except ValueError:
            return None
    if kind == "hat":
        try:
            vendor, product, direction = rest.split(":")
            return vendor.upper() + product.upper(), "Joy_POV1" + direction
        except ValueError:
            return None
    return None                                   # mouse buttons: not looked up


def describe_control(spec, devices=()):
    """A plain-English name for a control, like 'X52 button 7'."""
    kind, _, rest = (spec or "").partition(":")
    if kind == "key":
        return "keyboard %s" % rest
    if kind == "mouse":
        return "mouse button %s" % rest
    names = {d["ident"]: d["name"] for d in devices}
    try:
        vendor, product, last = rest.split(":")
    except ValueError:
        return spec
    name = names.get("%s:%s" % (vendor, product)) or "joystick %s:%s" % (vendor, product)
    if "x52" in name.lower().replace(" ", "").replace("-", ""):
        name = "X52"
    return "%s %s %s" % (name, "hat" if kind == "hat" else "button", last)


@dataclass
class Recording:
    name: str
    seconds: float
    created: str = ""
    devices: List[dict] = field(default_factory=list)
    binds_file: str = ""
    binds_devices: List[str] = field(default_factory=list)
    start_state: Dict = field(default_factory=dict)
    events: List[dict] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self):
        return {"program": "Starling button recorder", "name": self.name, "seconds": round(self.seconds, 2),
                "created": self.created, "devices": self.devices, "binds_file": self.binds_file,
                "binds_devices": self.binds_devices, "start_state": self.start_state, "notes": self.notes,
                "events": self.events}


class _JournalTap:
    """Looks like the EventProcessor, but only keeps the event names."""

    def __init__(self, sink):
        self.sink = sink

    def handle_line(self, line, silent=False):
        if silent:
            return
        from journal.parser import extract_event_name
        name = extract_event_name(line)
        if name and name not in QUIET_JOURNAL:
            self.sink(name)


def _flag_names(value, table):
    return {table.get(bit, "bit%d" % bit) for bit in range(32) if value & (1 << bit)}


class InputRecorder:
    def __init__(self, reader, journal_folder=None, clock=time.monotonic, sleep=time.sleep, poll=POLL_SECONDS,
                 status_reader=None, journal_factory=None):
        self.reader = reader
        self.journal_folder = Path(journal_folder) if journal_folder else None
        self.clock = clock
        self.sleep = sleep
        self.poll = poll
        self._status_reader = status_reader
        self._journal_factory = journal_factory

    # ---- reading the controls ----
    def _held_now(self, devices):
        """Everything held right now, as a set of specs."""
        down = set()
        for code in self.reader.keyboard.all_down():
            if code in VK_NAME:
                down.add(key_spec(VK_NAME[code]))
            elif code in MOUSE_NAME:
                down.add(mouse_spec(MOUSE_NAME[code]))
        for device in devices:
            mask, hat = self.reader.joy_state(device)
            if mask:
                for button in range(1, min(device.buttons or 32, 32) + 1):
                    if mask & (1 << (button - 1)):
                        down.add(joy_spec(device, button))
            for direction in hat_directions(hat):
                down.add(hat_spec(device, direction))
        return down

    # ---- reading the game ----
    def _read_status(self):
        if self._status_reader is not None:
            return self._status_reader()
        if self.journal_folder is None:
            return None
        try:
            with open(self.journal_folder / "Status.json", "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            return None

    def _make_journal(self, sink):
        if self._journal_factory is not None:
            return self._journal_factory(sink)
        if self.journal_folder is None or not self.journal_folder.is_dir():
            return None
        from journal.watcher import JournalWatcher
        return JournalWatcher(self.journal_folder, _JournalTap(sink))

    @staticmethod
    def _screen_name(focus):
        if not focus:
            return "none"
        return SCREENS.get(focus, ("", "screen %s" % focus))[1]

    # ---- the recording ----
    def record(self, name, seconds, stop=lambda: False, on_event=None, on_tick=None):
        recording = Recording(name=name, seconds=0.0, created=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        devices = list(self.reader.devices(force=True))
        recording.devices = [{"ident": d.ident, "name": d.name, "buttons": d.buttons, "x52": d.is_x52()} for d in devices]
        if not devices:
            recording.notes.append("No joystick was found by Windows, so only keyboard and mouse buttons were recorded.")

        state = {"gui": None, "flags": 0, "flags2": 0, "t": 0.0}

        def add(event):
            recording.events.append(event)
            if on_event:
                on_event(event)

        def journal_sink(event_name):
            add({"t": round(state["t"], 3), "type": "journal", "name": event_name})

        journal = self._make_journal(journal_sink)
        if self.journal_folder is not None and journal is None:
            recording.notes.append("The Elite journal folder was not found, so game events were not recorded.")
        if journal is not None:
            try:
                journal.poll_once()               # reads what is already there quietly, so only NEW events show
            except Exception:
                log.exception("Could not start reading the journal")
                journal = None
        status = self._read_status()
        if status is not None:
            state["gui"] = int(status.get("GuiFocus") or 0)
            state["flags"], state["flags2"] = int(status.get("Flags") or 0), int(status.get("Flags2") or 0)
            recording.start_state = {
                "screen": self._screen_name(state["gui"]),
                "switches_on": sorted(_flag_names(state["flags"], FLAGS_NAMES) | _flag_names(state["flags2"], FLAGS2_NAMES))}
        elif self.journal_folder is not None:
            recording.notes.append("Status.json could not be read, so screens and switches were not recorded.")

        previous, pressed_at = set(), {}
        start = self.clock()
        next_context = start
        while True:
            now = self.clock()
            t = now - start
            state["t"] = t
            if t >= seconds or stop():
                break
            try:
                current = self._held_now(devices)
            except Exception:
                log.exception("Could not read the buttons")
                current = previous
            for spec in sorted(current - previous):
                pressed_at[spec] = t
                add({"t": round(t, 3), "type": "down", "control": spec,
                     "with": sorted(previous & current), "screen": state["gui"]})
            for spec in sorted(previous - current):
                add({"t": round(t, 3), "type": "up", "control": spec, "held": round(t - pressed_at.pop(spec, t), 3)})
            previous = current
            if now >= next_context:
                next_context = now + CONTEXT_SECONDS
                self._read_context(state, t, add, journal)
            if on_tick:
                on_tick(t)
            self.sleep(self.poll)

        end = self.clock() - start
        for spec in sorted(previous):             # still held when time ran out
            add({"t": round(end, 3), "type": "up", "control": spec,
                 "held": round(end - pressed_at.get(spec, end), 3), "cut_off": True})
        recording.seconds = end
        return recording

    def _read_context(self, state, t, add, journal):
        if journal is not None:
            try:
                journal.poll_once()
            except Exception:
                log.exception("Could not read the journal")
        status = self._read_status()
        if status is None:
            return
        focus = int(status.get("GuiFocus") or 0)
        if focus != state["gui"]:
            add({"t": round(t, 3), "type": "screen", "name": self._screen_name(focus), "focus": focus})
            state["gui"] = focus
        for key, table in (("Flags", FLAGS_NAMES), ("Flags2", FLAGS2_NAMES)):
            value = int(status.get(key) or 0)
            old = state["flags" if key == "Flags" else "flags2"]
            if value != old:
                for name in sorted(_flag_names(value, table) - _flag_names(old, table)):
                    add({"t": round(t, 3), "type": "switch", "name": name, "on": True})
                for name in sorted(_flag_names(old, table) - _flag_names(value, table)):
                    add({"t": round(t, 3), "type": "switch", "name": name, "on": False})
                state["flags" if key == "Flags" else "flags2"] = value


# ---------------------------------------------------------------------------
# the report
# ---------------------------------------------------------------------------
VARIANT_SUFFIXES = ("_Buggy", "_Humanoid", "_Fighter", "_MultiCrew")
VARIANT_PREFIXES = ("Humanoid", "Vanity", "FreeCam", "MultiCrew", "HeadLook")
MENU_ACTIONS = {"CycleNextPanel", "CyclePreviousPanel", "FocusLeftPanel", "FocusRightPanel", "FocusCommsPanel",
                "FocusRadarPanel", "UIFocus"}


def _is_variant(action):
    return action.endswith(VARIANT_SUFFIXES) or action.startswith(VARIANT_PREFIXES)


def _is_menu(action):
    return action.startswith("UI_") or action in MENU_ACTIONS


def _base_action(action):
    for suffix in VARIANT_SUFFIXES:
        if action.endswith(suffix):
            return action[:-len(suffix)]
    return action


def _stick_names(spec, devices):
    parts = spec.split(":")
    ident = ":".join(parts[1:3]) if len(parts) >= 4 else ""
    return [d["name"] for d in devices if d["ident"] == ident]


def _matches(book, event, devices=()):
    """The Elite actions this press triggers, best first (empty if unknown)."""
    if book is None:
        return []
    mine = elite_control(event["control"])
    if mine is None:
        return []
    held = [elite_control(s) for s in event.get("with", [])]
    found = book.actions_for(mine[0], mine[1], [h for h in held if h], names=_stick_names(event["control"], devices))
    in_menu = bool(event.get("screen"))           # a screen is open: menu actions first, otherwise ship actions first
    found.sort(key=lambda m: (not m.sure, -len(m.modifiers), _is_variant(m.action), _is_menu(m.action) != in_menu))
    return found


def _has_keyboard_key(book, action):
    if book is None:
        return None
    keystroke, _why = book.lookup(action)
    return keystroke is not None


def analyse(recording, book):
    """Each press with its matches. Returns a list of dicts: {event, up, matches, shift}."""
    presses = []
    open_presses = {}
    for event in recording.events:
        if event["type"] == "down":
            entry = {"event": event, "up": None, "matches": _matches(book, event, recording.devices), "shift": False}
            presses.append(entry)
            open_presses[event["control"]] = entry
        elif event["type"] == "up" and event["control"] in open_presses:
            open_presses.pop(event["control"])["up"] = event
    for entry in presses:                          # which presses were only "shift" buttons for a later press?
        kind, _, rest = entry["event"]["control"].partition(":")
        if kind == "key" and rest in KEYBOARD_MODIFIERS:
            entry["shift"] = True
    for entry in presses:
        for shift_control in entry["event"].get("with", []):
            if entry["matches"] and entry["matches"][0].modifiers:
                for other in presses:
                    if other["event"]["control"] == shift_control and other["event"]["t"] <= entry["event"]["t"]:
                        other["shift"] = True
    return presses


def _fmt(seconds):
    return ("%g" % round(seconds, 2))


def suggest_macro(recording, book):
    """(steps, notes). Steps are in Starling's macro format. Notes list anything that needs your attention."""
    presses = [p for p in analyse(recording, book) if not p["shift"]]
    steps, notes = [], []
    last_end = None
    last_action = None
    for entry in presses:
        event, up = entry["event"], entry["up"]
        label = describe_control(event["control"], recording.devices)
        if not entry["matches"]:
            notes.append("%.2fs  %s is not in your Elite controls file, so it is left out of the macro." % (event["t"], label))
            continue
        action = entry["matches"][0].action
        base = _base_action(action)
        if base != action and book is not None and book.has_action(base):
            notes.append("%.2fs  %s matched %s (the SRV/other-vehicle version). Using the ship action %s instead." % (event["t"], label, action, base))
            action = base
        if not entry["matches"][0].sure:
            notes.append("%.2fs  %s matched %s by button number only - check this one." % (event["t"], label, action))
        if _has_keyboard_key(book, action) is False:
            notes.append("%s has no keyboard key in Elite. Starling can only press keyboard keys: bind a spare key to %s in the game's controls." % (action, action))
        held = up["held"] if up else 0.0
        gap = event["t"] - last_end if last_end is not None else 0.0
        if last_end is None:
            gap = 0.0
        is_hold = held >= HOLD_MIN
        if (not is_hold and steps and last_action == action and gap < REPEAT_GAP and _is_press(steps[-1], action)):
            steps[-1] = _bump(steps[-1], action)
        else:
            if last_end is not None and gap >= WAIT_MIN:
                steps.append("wait " + _fmt(min(WAIT_MAX, round(gap / WAIT_STEP) * WAIT_STEP)))
            steps.append("hold %s %s" % (action, _fmt(min(WAIT_MAX, round(held, 1)))) if is_hold else action)
        last_action = action
        last_end = event["t"] + (held if is_hold else 0.05)
    return steps, notes


def _is_press(step, action):
    return step == action or re.fullmatch(re.escape(action) + r" x\d+", step) is not None


def _bump(step, action):
    match = re.fullmatch(re.escape(action) + r" x(\d+)", step)
    return "%s x%d" % (action, (int(match.group(1)) if match else 1) + 1)


def format_report(recording, book):
    """The whole report as a list of text lines."""
    lines = ["STARLING BUTTON RECORDING: %s" % recording.name,
             "Recorded %s for %.1f seconds." % (recording.created, recording.seconds), ""]
    lines.append("Joysticks Windows can see:")
    if recording.devices:
        for d in recording.devices:
            lines.append("  %s  [%s]  %d buttons%s" % (d["name"], d["ident"], d["buttons"], "  <- X52" if d["x52"] else ""))
    else:
        lines.append("  none")
    if recording.binds_file:
        lines.append("Your Elite controls file: %s" % recording.binds_file)
    if recording.binds_devices:
        lines.append("Joystick names in that file: %s" % ", ".join(recording.binds_devices))
    if recording.start_state:
        lines.append("At the start: screen = %s; switches on = %s" % (
            recording.start_state.get("screen"), ", ".join(recording.start_state.get("switches_on", [])) or "none"))
    lines += [""] + ["Note: " + n for n in recording.notes]
    lines += ["", "TIMELINE (seconds from the start)", "-" * 60]
    presses = {id(p["event"]): p for p in analyse(recording, book)}
    pressed = 0
    for event in recording.events:
        t = "%6.2fs" % event["t"]
        kind = event["type"]
        if kind == "down":
            pressed += 1
            entry = presses[id(event)]
            label = describe_control(event["control"], recording.devices)
            if entry["matches"]:
                first = entry["matches"][0]
                text = "-> %s%s" % (first.action, "" if first.sure else " (?)")
                more = [m.action for m in entry["matches"][1:4]]
                if more:
                    text += "   (also: %s)" % ", ".join(more)
            else:
                text = "-> (not found in your Elite controls file)" if book is not None and elite_control(event["control"]) else "-> (no lookup)"
            shifted = ""
            if event.get("with"):
                shifted = "   while holding " + ", ".join(describe_control(s, recording.devices) for s in event["with"])
            lines.append("%s  PRESS    %-26s %s%s" % (t, label, text, shifted))
        elif kind == "up":
            lines.append("%s  release  %-26s held %.2fs%s" % (
                t, describe_control(event["control"], recording.devices), event["held"],
                "  (still held when recording stopped)" if event.get("cut_off") else ""))
        elif kind == "screen":
            lines.append("%s  SCREEN   %s" % (t, event["name"]))
        elif kind == "switch":
            lines.append("%s  SWITCH   %s %s" % (t, event["name"], "ON" if event["on"] else "off"))
        elif kind == "journal":
            lines.append("%s  JOURNAL  %s" % (t, event["name"]))
    if not pressed:
        lines.append("  Nothing was pressed.")
    steps, notes = suggest_macro(recording, book)
    lines += ["", "SUGGESTED MACRO", "-" * 60]
    if steps:
        key = re.sub(r"[^a-z0-9_]+", "_", recording.name.lower()).strip("_") or "my_macro"
        lines.append("Put this in config\\settings.json (replace  %s  with the id of the command it belongs to):" % key)
        lines.append(json.dumps({"macros": {key: steps}}, indent=2))
    else:
        lines.append("  No steps could be made (nothing pressed matched your Elite controls).")
    lines += [""] + ["Check: " + n for n in notes]
    lines += ["", "(Stick movement and sliders are not recorded. Only the first 32 buttons and one hat per joystick can be seen.)"]
    return lines


def save_recording(recording, book, folder):
    """Writes name_stamp.txt (readable) and name_stamp.json (raw) into folder. Returns (txt_path, json_path)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", recording.name).strip("_") or "recording"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt, raw = folder / ("%s_%s.txt" % (safe, stamp)), folder / ("%s_%s.json" % (safe, stamp))
    txt.write_text("\n".join(format_report(recording, book)) + "\n", encoding="utf-8")
    data = recording.to_dict()
    data["resolved"] = [{"t": p["event"]["t"], "control": p["event"]["control"], "shift_only": p["shift"],
                         "actions": [(m.action + ("" if m.sure else "?")) for m in p["matches"]]}
                        for p in analyse(recording, book)]
    raw.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return txt, raw
