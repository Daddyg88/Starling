"""Which screen the biology list belongs on. No window code, so it can be tested.

Windows numbers its screens in a way that is hard to guess, and Tk only knows about the MAIN screen, so the overlay used to
appear on the main screen even when Elite was running on another one. 'Automatic' now finds the screen Elite's window is on.
Screens are rectangles in Windows' desktop coordinates: the main screen starts at (0, 0), and a screen to the left or above
it has negative numbers.
"""
import sys
from collections import namedtuple

Screen = namedtuple("Screen", "left top right bottom")
ELITE_TITLE = "Elite - Dangerous"
CHOICES = [("Automatic (the screen Elite is on)", "auto"), ("The main Windows screen", "primary"),
           ("Screen 1 (leftmost)", "1"), ("Screen 2", "2"), ("Screen 3", "3"), ("Screen 4", "4")]


def is_primary(screen):
    return screen.left <= 0 < screen.right and screen.top <= 0 < screen.bottom


def screen_containing(screens, x, y):
    for screen in screens:
        if screen.left <= x < screen.right and screen.top <= y < screen.bottom:
            return screen
    return None


def pick_screen(choice, screens, elite_point=None):
    """The screen to use, or None when there is nothing to choose from (the caller then uses the main screen)."""
    if not screens:
        return None
    choice = str(choice or "auto").strip().lower()
    primary = next((s for s in screens if is_primary(s)), screens[0])
    if choice == "primary":
        return primary
    if choice.isdigit():
        ordered = sorted(screens, key=lambda s: (s.left, s.top))
        number = int(choice)
        return ordered[number - 1] if 1 <= number <= len(ordered) else primary
    if elite_point is not None:
        found = screen_containing(screens, elite_point[0], elite_point[1])
        if found is not None:
            return found
    return primary


def list_screens():
    """Every screen Windows knows about (empty on other systems or if Windows says no)."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes
    found = []
    proc = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(wintypes.RECT), ctypes.c_void_p)
    ctypes.windll.user32.EnumDisplayMonitors.argtypes = [ctypes.c_void_p, ctypes.c_void_p, proc, ctypes.c_void_p]

    def callback(_monitor, _dc, rect, _data):
        r = rect.contents
        found.append(Screen(r.left, r.top, r.right, r.bottom))
        return 1
    keep = proc(callback)                                  # kept in a name so it cannot be freed during the call
    ctypes.windll.user32.EnumDisplayMonitors(None, None, keep, None)
    return found


def elite_point():
    """The middle of Elite's window, or None when the game is not running (or this is not Windows)."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    hits = []
    proc = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _data):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length:
                buffer = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buffer, length + 1)
                if buffer.value.startswith(ELITE_TITLE):
                    hits.append(hwnd)
        return 1
    keep = proc(callback)
    enum = ctypes.WinDLL("user32").EnumWindows         # a private copy, so it cannot clash with the sender's EnumWindows
    enum.argtypes = [proc, wintypes.LPARAM]
    enum(keep, 0)
    if not hits:
        return None
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hits[0], ctypes.byref(rect)):
        return None
    return (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2


def overlay_rect(choice, fallback_size, screens=None, point=None):
    """(left, top, width, height) of the screen to draw on. fallback_size is Tk's idea of the main screen."""
    try:
        screens = list_screens() if screens is None else screens
        needs_point = str(choice or "auto").strip().lower() in ("", "auto")
        point = (elite_point() if needs_point else None) if point is None else point
        chosen = pick_screen(choice, screens, point)
    except Exception:
        chosen = None
    if chosen is None:
        return 0, 0, fallback_size[0], fallback_size[1]
    return chosen.left, chosen.top, chosen.right - chosen.left, chosen.bottom - chosen.top
