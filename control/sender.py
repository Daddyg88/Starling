"""
Presses keys for STARLING (Windows only).

SAFETY RULES
  * Keys are only pressed while Elite Dangerous is the window you are looking at.
    (Otherwise "lower the gear" could type letters into your browser or Discord.)
  * Every key that goes down comes back up, even if something goes wrong in between.

The real Windows calls live in WindowsKeyboard at the bottom; everything else works with any
object that has key_event(scancode, extended, down), so it can be tested without Windows.
"""

import sys
import time

from control import keys
from core.logger import get_logger

log = get_logger("sender")

GAME_WINDOW_WORDS = ("elite - dangerous", "elite dangerous")

# Reasons a press can fail (the runner turns each into a sentence)
OK = ""
NOT_WINDOWS = "not_windows"
GAME_NOT_ACTIVE = "game_not_active"
UNKNOWN_KEY = "unknown_key"
FAILED = "failed"


class KeySender:
    def __init__(self, keyboard=None, focus_check=None, sleep=time.sleep, hold_seconds=0.06,
                 require_game=True):
        self.keyboard = keyboard
        self.focus_check = focus_check
        self.sleep = sleep
        self.hold_seconds = hold_seconds
        self.require_game = require_game

    def _ready(self):
        if self.keyboard is None:
            if sys.platform != "win32":
                return NOT_WINDOWS
            self.keyboard = WindowsKeyboard()
        if self.focus_check is None:
            self.focus_check = game_is_active
        return OK

    def send(self, keystroke, hold=None):
        """Press a Keystroke (modifiers held, key tapped, or held for `hold` seconds). Returns "" or a reason it did not happen."""
        problem = self._ready()
        if problem:
            return problem
        codes = []
        for name in (*keystroke.modifiers, keystroke.key):
            code = keys.scancode_for(name)
            if code is None:
                return UNKNOWN_KEY
            codes.append(code)
        if self.require_game and not self.focus_check():
            return GAME_NOT_ACTIVE
        pressed = []
        try:
            for scancode, extended in codes:
                self.keyboard.key_event(scancode, extended, True)
                pressed.append((scancode, extended))
                if len(pressed) < len(codes):
                    self.sleep(0.02)
            self.sleep(self.hold_seconds if hold is None else hold)
        except Exception:
            log.exception("Key press failed")
            return FAILED
        finally:
            for scancode, extended in reversed(pressed):
                try:
                    self.keyboard.key_event(scancode, extended, False)
                except Exception:
                    log.exception("Could not release a key")
                self.sleep(0.01)
        return OK


# ---------------------------------------------------------------------------
# The real Windows part (not used in tests)
# ---------------------------------------------------------------------------
OVERLAY_WORDS = ("void compass", "voidcompass")      # overlay programs that may sit in front of the game


def _is_game(title):
    return any(word in (title or "").lower() for word in GAME_WINDOW_WORDS)


def _is_overlay(title, process):
    text = "%s %s" % ((title or "").lower(), (process or "").lower())
    return any(word in text for word in OVERLAY_WORDS)


def game_is_active(win=None, sleep=time.sleep):
    """
    True if keys can safely go to Elite Dangerous.
      * Elite is the window in front: yes.
      * An overlay such as Void Compass is in front (it can take the focus when its overlays are shown) and Elite is
        running: bring Elite to the front first, then yes once it is there.
      * Anything else (browser, Discord...): no. The reason goes in logs\starling.log.
    """
    if win is None:
        if sys.platform != "win32":
            return False
        win = _windows()
    hwnd, title, process = win.foreground()
    if _is_game(title):
        return True
    if _is_overlay(title, process):
        game = win.find_game()
        if game:
            log.info("%s is in front, bringing Elite Dangerous forward", title or process)
            win.bring_forward(game)
            for _ in range(10):
                sleep(0.05)
                if _is_game(win.foreground()[1]):
                    return True
            log.warning("Could not bring Elite Dangerous forward from %s", title or process)
            return False
    log.info("Not pressing keys: the window in front is %r (%s), not Elite Dangerous", title, process)
    return False


_WINDOWS = None


def _windows():
    global _WINDOWS
    if _WINDOWS is None:
        _WINDOWS = WindowsWindows()
    return _WINDOWS


class WindowsWindows:
    """Asks Windows about windows: which is in front, where Elite is, and bringing it forward (Windows only)."""

    def __init__(self):
        import ctypes
        self.ctypes = ctypes
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32

    def _title(self, handle):
        length = self.user32.GetWindowTextLengthW(handle)
        buffer = self.ctypes.create_unicode_buffer(length + 1)
        self.user32.GetWindowTextW(handle, buffer, length + 1)
        return buffer.value

    def _process_name(self, handle):
        ctypes = self.ctypes
        pid = ctypes.c_ulong(0)
        self.user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        opened = self.kernel32.OpenProcess(0x1000, False, pid.value)      # PROCESS_QUERY_LIMITED_INFORMATION
        if not opened:
            return ""
        try:
            size = ctypes.c_ulong(520)
            buffer = ctypes.create_unicode_buffer(size.value)
            if self.kernel32.QueryFullProcessImageNameW(opened, 0, buffer, ctypes.byref(size)):
                return buffer.value.rsplit("\\", 1)[-1]
            return ""
        finally:
            self.kernel32.CloseHandle(opened)

    def foreground(self):
        handle = self.user32.GetForegroundWindow()
        if not handle:
            return 0, "", ""
        return handle, self._title(handle), self._process_name(handle)

    def find_game(self):
        ctypes = self.ctypes
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def visit(handle, _param):
            if self.user32.IsWindowVisible(handle) and _is_game(self._title(handle)):
                found.append(handle)
                return False
            return True
        self.user32.EnumWindows(visit, 0)
        return found[0] if found else 0

    def bring_forward(self, handle):
        user32, kernel32 = self.user32, self.kernel32
        try:
            if user32.IsIconic(handle):
                user32.ShowWindow(handle, 9)                                # SW_RESTORE
            front = user32.GetForegroundWindow()
            front_thread = user32.GetWindowThreadProcessId(front, None) if front else 0
            this_thread = kernel32.GetCurrentThreadId()
            attached = bool(front_thread and front_thread != this_thread
                            and user32.AttachThreadInput(this_thread, front_thread, True))
            try:
                user32.SetForegroundWindow(handle)
            finally:
                if attached:
                    user32.AttachThreadInput(this_thread, front_thread, False)
            return True
        except Exception:
            log.exception("Could not bring Elite Dangerous forward")
            return False


def make_input_structures():
    """
    The structures SendInput needs. Fixed-size types are used on purpose so the layout is identical
    everywhere (on 64-bit Windows an INPUT is exactly 40 bytes; the tests check that).
    """
    import ctypes

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_uint16), ("wScan", ctypes.c_uint16), ("dwFlags", ctypes.c_uint32),
                    ("time", ctypes.c_uint32), ("dwExtraInfo", ctypes.c_size_t)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", ctypes.c_int32), ("dy", ctypes.c_int32), ("mouseData", ctypes.c_uint32),
                    ("dwFlags", ctypes.c_uint32), ("time", ctypes.c_uint32), ("dwExtraInfo", ctypes.c_size_t)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", ctypes.c_uint32), ("wParamL", ctypes.c_uint16), ("wParamH", ctypes.c_uint16)]

    class INPUTUNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_uint32), ("u", INPUTUNION)]

    return INPUT, INPUTUNION, KEYBDINPUT


class WindowsKeyboard:
    """Sends hardware-style key presses with the Windows SendInput function."""

    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008

    def __init__(self):
        import ctypes
        self.ctypes = ctypes
        self._INPUT, self._UNION, self._KEYBDINPUT = make_input_structures()
        self._send = ctypes.windll.user32.SendInput

    def key_event(self, scancode, extended, down):
        flags = self.KEYEVENTF_SCANCODE
        if extended:
            flags |= self.KEYEVENTF_EXTENDEDKEY
        if not down:
            flags |= self.KEYEVENTF_KEYUP
        item = self._INPUT(type=1, u=self._UNION(ki=self._KEYBDINPUT(0, scancode, flags, 0, 0)))
        sent = self._send(1, self.ctypes.byref(item), self.ctypes.sizeof(item))
        if sent != 1:
            raise OSError("SendInput did not send the key (Windows blocked it)")
