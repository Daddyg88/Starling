"""
Elite Dangerous key names -> the keyboard "scancodes" Windows needs.

Elite's .binds files call keys things like  Key_L , Key_LeftShift , Key_Numpad_0.
To press one we need its hardware scancode (Elite reads the keyboard that way, so
ordinary "virtual key" presses are ignored by the game).

If the game uses a key name that is not in this table, STARLING says so out loud and in the log
instead of guessing. To teach her a new key, add one line to _TABLE.
"""

import re

# name (lower case, after "Key_") -> (scancode, extended)
_TABLE = {}


def _add(names, code, extended=False):
    for name in names.split():
        _TABLE[name.lower()] = (code, extended)


# letters and number row
for _i, _c in enumerate("qwertyuiop"):
    _add(_c, 0x10 + _i)
for _i, _c in enumerate("asdfghjkl"):
    _add(_c, 0x1E + _i)
for _i, _c in enumerate("zxcvbnm"):
    _add(_c, 0x2C + _i)
for _i, _c in enumerate("1234567890"):
    _add(_c, 0x02 + _i)

_add("Escape Esc", 0x01)
_add("Minus", 0x0C)
_add("Equals Equal", 0x0D)
_add("Backspace", 0x0E)
_add("Tab", 0x0F)
_add("LeftBracket", 0x1A)
_add("RightBracket", 0x1B)
_add("Enter Return", 0x1C)
_add("LeftControl LeftCtrl", 0x1D)
_add("SemiColon Semicolon", 0x27)
_add("Apostrophe Quote", 0x28)
_add("Grave Tilde BackQuote", 0x29)
_add("LeftShift", 0x2A)
_add("BackSlash Backslash", 0x2B)
_add("Comma", 0x33)
_add("Period FullStop", 0x34)
_add("Slash ForwardSlash", 0x35)
_add("RightShift", 0x36)
_add("LeftAlt", 0x38)
_add("Space", 0x39)
_add("CapsLock", 0x3A)
for _i in range(10):
    _add("F%d" % (_i + 1), 0x3B + _i)
_add("F11", 0x57)
_add("F12", 0x58)
_add("NumLock", 0x45)
_add("ScrollLock", 0x46)

# number pad
for _i, _code in enumerate((0x52, 0x4F, 0x50, 0x51, 0x4B, 0x4C, 0x4D, 0x47, 0x48, 0x49)):
    _add("Numpad_%d" % _i, _code)
_add("Numpad_Multiply", 0x37)
_add("Numpad_Subtract", 0x4A)
_add("Numpad_Add", 0x4E)
_add("Numpad_Decimal", 0x53)
_add("Numpad_Enter", 0x1C, True)
_add("Numpad_Divide", 0x35, True)

# the grey keys (these need the "extended" flag)
_add("RightControl RightCtrl", 0x1D, True)
_add("RightAlt", 0x38, True)
_add("Home", 0x47, True)
_add("UpArrow", 0x48, True)
_add("PageUp", 0x49, True)
_add("LeftArrow", 0x4B, True)
_add("RightArrow", 0x4D, True)
_add("End", 0x4F, True)
_add("DownArrow", 0x50, True)
_add("PageDown", 0x51, True)
_add("Insert", 0x52, True)
_add("Delete", 0x53, True)

MODIFIER_NAMES = {"leftshift", "rightshift", "leftcontrol", "rightcontrol", "leftctrl", "rightctrl",
                  "leftalt", "rightalt"}


def _clean(name):
    name = (name or "").strip()
    if name.lower().startswith("key_"):
        name = name[4:]
    return re.sub(r"\s+", "", name).lower()


def scancode_for(key_name):
    """('Key_L') -> (0x26, False). Returns None if STARLING does not know that key."""
    return _TABLE.get(_clean(key_name))


def is_known(key_name):
    return scancode_for(key_name) is not None


def nice_name(key_name):
    """Key_LeftShift -> 'Left Shift', Key_Numpad_0 -> 'Numpad 0' (used when she tells you what she pressed)."""
    name = (key_name or "").strip()
    if name.lower().startswith("key_"):
        name = name[4:]
    name = name.replace("_", " ")
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
