"""
Reading buttons: keyboard keys, mouse side buttons and joystick buttons (your Saitek / Logitech X52).

A button is stored in settings as a short piece of text, called a "spec":
    key:F13               a keyboard key
    mouse:X1              the mouse side button
    joy:06A3:075C:7       button 7 on the joystick with USB id 06A3:075C  (the X52)

Windows does the actual reading (GetAsyncKeyState for keys and mouse, the "winmm" joystick service for
joysticks - both are built into Windows, nothing to install). The classes at the bottom talk to Windows;
everything above them works with any stand-in object, so it can be tested without a joystick.

LIMITS you should know about
  * winmm can see 32 buttons per device. The X52 has more if you count its "mode" shifts; the extra ones
    cannot be seen this way. Pick one of the first 32 (the Learn button only ever finds those).
  * The key you choose still reaches the game. Pick one the game does not use (F13-F24, Scroll Lock, a spare
    joystick button, a mouse side button).
"""

import sys
import time
from dataclasses import dataclass
from typing import List, Optional

from core.logger import get_logger

log = get_logger("inputs")

SAITEK_X52_PRODUCT = 0x075C
X52_VENDORS = {0x06A3, 0x046D, 0x0738}      # Saitek, Logitech, Mad Catz (the X52 has been sold under all three)

# keyboard key names -> Windows virtual key codes
VK = {"Backspace": 0x08, "Tab": 0x09, "Pause": 0x13, "CapsLock": 0x14, "Space": 0x20, "PageUp": 0x21, "PageDown": 0x22,
      "End": 0x23, "Home": 0x24, "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28, "Insert": 0x2D,
      "Delete": 0x2E, "Menu": 0x5D, "NumLock": 0x90, "ScrollLock": 0x91,
      "LeftShift": 0xA0, "RightShift": 0xA1, "LeftCtrl": 0xA2, "RightCtrl": 0xA3, "LeftAlt": 0xA4, "RightAlt": 0xA5,
      "Semicolon": 0xBA, "Equals": 0xBB, "Comma": 0xBC, "Minus": 0xBD, "Period": 0xBE, "Slash": 0xBF, "Grave": 0xC0,
      "LeftBracket": 0xDB, "Backslash": 0xDC, "RightBracket": 0xDD, "Quote": 0xDE,
      "NumpadMultiply": 0x6A, "NumpadAdd": 0x6B, "NumpadSubtract": 0x6D, "NumpadDecimal": 0x6E, "NumpadDivide": 0x6F}
for _i in range(10):
    VK["%d" % _i] = 0x30 + _i
    VK["Numpad%d" % _i] = 0x60 + _i
for _i in range(26):
    VK[chr(65 + _i)] = 0x41 + _i
for _i in range(24):
    VK["F%d" % (_i + 1)] = 0x70 + _i
VK_NAME = {code: name for name, code in VK.items()}
MOUSE = {"X1": 0x05, "X2": 0x06, "Middle": 0x04}      # left and right click are never allowed
MOUSE_NAME = {code: name for name, code in MOUSE.items()}


@dataclass(frozen=True)
class JoyDevice:
    index: int            # 0-15, Windows' own numbering (can change when you plug things in)
    vendor: int
    product: int
    name: str
    buttons: int          # how many buttons Windows says it has (max 32)

    @property
    def ident(self):
        return "%04X:%04X" % (self.vendor, self.product)

    def is_x52(self):
        return ("x52" in self.name.lower().replace("-", "").replace(" ", "")
                or self.product == SAITEK_X52_PRODUCT and self.vendor in X52_VENDORS)


# ---------------------------------------------------------------------------
# specs
# ---------------------------------------------------------------------------
def hat_directions(value):
    """The hat's number (0 = up, 9000 = right, 18000 = down, 27000 = left, 65535 = centred) -> {"Up", "Right", ...}."""
    if value is None or value < 0 or value >= 36000:
        return set()
    found = set()
    if value <= 4500 or value >= 31500:
        found.add("Up")
    if 4500 <= value <= 13500:
        found.add("Right")
    if 13500 <= value <= 22500:
        found.add("Down")
    if 22500 <= value <= 31500:
        found.add("Left")
    return found


def hat_spec(device, direction):
    return "hat:%s:%s" % (device.ident, direction)


def key_spec(name):
    return "key:%s" % name


def mouse_spec(name):
    return "mouse:%s" % name


def joy_spec(device, button):
    return "joy:%s:%d" % (device.ident, button)


def parse_spec(spec):
    """'joy:06A3:075C:7' -> ('joy', '06A3:075C', 7); 'key:F13' -> ('key', 0x7C); None if it is not understood."""
    try:
        kind, _, rest = (spec or "").partition(":")
        if kind == "key" and rest in VK:
            return ("key", VK[rest])
        if kind == "mouse" and rest in MOUSE:
            return ("mouse", MOUSE[rest])
        if kind == "joy":
            vendor, product, button = rest.split(":")
            button = int(button)
            if 1 <= button <= 32:
                return ("joy", "%s:%s" % (vendor.upper(), product.upper()), button)
    except ValueError:
        pass
    return None


def describe(spec, devices=()):
    parsed = parse_spec(spec)
    if parsed is None:
        return "Not set"
    if parsed[0] == "key":
        return "Keyboard: %s" % VK_NAME.get(parsed[1], "?")
    if parsed[0] == "mouse":
        return "Mouse button %s" % MOUSE_NAME.get(parsed[1], "?")
    for device in devices:
        if device.ident == parsed[1]:
            return "%s: button %d" % (device.name, parsed[2])
    return "Joystick %s: button %d (not plugged in)" % (parsed[1], parsed[2])


# ---------------------------------------------------------------------------
# the reader
# ---------------------------------------------------------------------------
class ButtonReader:
    """Asks Windows (or a stand-in) whether a given button is held down."""

    REFRESH_SECONDS = 2.0

    def __init__(self, keyboard=None, joysticks=None, clock=time.monotonic):
        self.keyboard = keyboard if keyboard is not None else WindowsKeys()
        self.joysticks = joysticks if joysticks is not None else WindowsJoysticks()
        self.clock = clock
        self._devices: List[JoyDevice] = []
        self._refreshed = -99.0

    def devices(self, force=False):
        now = self.clock()
        if force or now - self._refreshed > self.REFRESH_SECONDS:
            try:
                self._devices = list(self.joysticks.devices())
            except Exception:
                log.exception("Could not list joysticks")
                self._devices = []
            self._refreshed = now
        return self._devices

    def x52_devices(self):
        return [d for d in self.devices() if d.is_x52()]

    def is_down(self, spec):
        parsed = parse_spec(spec)
        if parsed is None:
            return False
        try:
            if parsed[0] in ("key", "mouse"):
                return bool(self.keyboard.is_down(parsed[1]))
            for device in self.devices():
                if device.ident == parsed[1]:
                    mask = self.joysticks.buttons(device.index)
                    return bool(mask is not None and mask & (1 << (parsed[2] - 1)))
        except Exception:
            log.exception("Could not read a button")
        return False

    def joy_state(self, device):
        """(button mask, hat number or None) for one joystick; (None, None) if it cannot be read."""
        try:
            if hasattr(self.joysticks, "state"):
                got = self.joysticks.state(device.index)
                return (None, None) if got is None else got
            return self.joysticks.buttons(device.index), None
        except Exception:
            log.exception("Could not read a joystick")
            return None, None

    def snapshot(self):
        """Everything currently held down, as a set of specs (used by Learn)."""
        down = set()
        try:
            for code in self.keyboard.all_down():
                if code in VK_NAME:
                    down.add(key_spec(VK_NAME[code]))
                elif code in MOUSE_NAME:
                    down.add(mouse_spec(MOUSE_NAME[code]))
            for device in self.devices(force=True):
                mask = self.joysticks.buttons(device.index) or 0
                for button in range(1, min(device.buttons or 32, 32) + 1):
                    if mask & (1 << (button - 1)):
                        down.add(joy_spec(device, button))
        except Exception:
            log.exception("Could not read the buttons")
        return down

    def learn(self, seconds=6.0, sleep=time.sleep, interval=0.03):
        """
        Wait for you to press a NEW button and return its spec (None if nothing was pressed in time).
        Buttons already held when it starts are ignored.
        """
        before = self.snapshot()
        end = self.clock() + seconds
        while self.clock() < end:
            for spec in sorted(self.snapshot() - before):
                return spec
            sleep(interval)
        return None


# ---------------------------------------------------------------------------
# The real Windows parts (not used in tests)
# ---------------------------------------------------------------------------
class WindowsKeys:
    def __init__(self):
        import ctypes
        self._get = ctypes.windll.user32.GetAsyncKeyState

    def is_down(self, vk):
        return bool(self._get(vk) & 0x8000)

    def all_down(self):
        return [vk for vk in list(VK_NAME) + list(MOUSE_NAME) if self._get(vk) & 0x8000]


class WindowsJoysticks:
    """The built-in Windows joystick service (winmm.dll)."""

    JOYERR_NOERROR = 0
    JOY_RETURNBUTTONS = 0x80
    JOY_RETURNPOV = 0x40

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class JOYCAPSW(ctypes.Structure):
            _fields_ = ([("wMid", wintypes.WORD), ("wPid", wintypes.WORD), ("szPname", ctypes.c_wchar * 32)]
                        + [(n, wintypes.UINT) for n in ("wXmin", "wXmax", "wYmin", "wYmax", "wZmin", "wZmax",
                                                         "wNumButtons", "wPeriodMin", "wPeriodMax", "wRmin", "wRmax",
                                                         "wUmin", "wUmax", "wVmin", "wVmax", "wCaps", "wMaxAxes",
                                                         "wNumAxes", "wMaxButtons")]
                        + [("szRegKey", ctypes.c_wchar * 32), ("szOEMVxD", ctypes.c_wchar * 260)])

        class JOYINFOEX(ctypes.Structure):
            _fields_ = [(n, wintypes.DWORD) for n in ("dwSize", "dwFlags", "dwXpos", "dwYpos", "dwZpos", "dwRpos",
                                                        "dwUpos", "dwVpos", "dwButtons", "dwButtonNumber", "dwPOV",
                                                        "dwReserved1", "dwReserved2")]

        self.ctypes, self.CAPS, self.INFO = ctypes, JOYCAPSW, JOYINFOEX
        self.winmm = ctypes.windll.winmm

    def devices(self):
        found = []
        for index in range(self.winmm.joyGetNumDevs()):
            caps = self.CAPS()
            if self.winmm.joyGetDevCapsW(index, self.ctypes.byref(caps), self.ctypes.sizeof(caps)) != self.JOYERR_NOERROR:
                continue
            if self.buttons(index) is None:
                continue                      # not plugged in
            name = _registry_name(caps.szRegKey, index) or caps.szPname or "Joystick %d" % (index + 1)
            found.append(JoyDevice(index, caps.wMid, caps.wPid, name, min(int(caps.wNumButtons), 32)))
        return found

    def buttons(self, index):
        info = self.INFO()
        info.dwSize = self.ctypes.sizeof(info)
        info.dwFlags = self.JOY_RETURNBUTTONS
        if self.winmm.joyGetPosEx(index, self.ctypes.byref(info)) != self.JOYERR_NOERROR:
            return None
        return int(info.dwButtons)

    def state(self, index):
        """(buttons, hat) in ONE call to Windows. The hat is a number in hundredths of a degree (65535 = centred)."""
        info = self.INFO()
        info.dwSize = self.ctypes.sizeof(info)
        info.dwFlags = self.JOY_RETURNBUTTONS | self.JOY_RETURNPOV
        if self.winmm.joyGetPosEx(index, self.ctypes.byref(info)) != self.JOYERR_NOERROR:
            return None
        return int(info.dwButtons), int(info.dwPOV)


def _registry_name(reg_key, index):
    """The friendly name Windows shows in 'Set up USB game controllers' (best effort)."""
    if sys.platform != "win32" or not reg_key:
        return ""
    import winreg
    config = r"System\CurrentControlSet\Control\MediaResources\Joystick\%s\CurrentJoystickSettings" % reg_key
    oem = r"System\CurrentControlSet\Control\MediaProperties\PrivateProperties\Joystick\OEM\%s"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, config) as key:
                oem_key = winreg.QueryValueEx(key, "Joystick%dOEMName" % (index + 1))[0]
            with winreg.OpenKey(hive, oem % oem_key) as key:
                return str(winreg.QueryValueEx(key, "OEMName")[0])
        except OSError:
            continue
    return ""
