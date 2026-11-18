"""
The chat window: Twitch and YouTube chat together in one Starling-style window you can drag and resize.

It is shown while chat is switched on (Settings > Streaming > "Let chat talk to Starling") AND "Show the chat window" is on. It is a
normal-looking dark window with a title bar made here (so it matches the dashboard): drag it by the top bar, resize it with the little
triangle in the bottom right corner, make the text bigger or smaller with A- and A+, pin it on top of other windows, or close it with X
(that switches "Show the chat window" off; switch it back on in Settings). Its position and size are remembered.

Windows: it never takes the keyboard focus from the game when you click it (the same "no activate" setting the overlays use).
Chat is READ only. Nothing typed here goes anywhere: there is no text box.

Two parts: the helpers (plain Python, tested) and ChatWindow (the tkinter window, runs inside the dashboard's loop).
"""

import time

from core.logger import get_logger
from ui import theme
from ui.window_memory import desktop_area, make_geometry, tk_geometry, parse_geometry, usable_geometry

log = get_logger("chat_window")

TICK_MS = 400
MIN_SIZE = (260, 160)
DEFAULT_SIZE = (380, 520)
FONT_SIZES = (10, 12, 14, 16, 18)
MAX_DRAWN = 300                  # lines kept in the window; older ones are removed from the top

TWITCH = "#B58CFF"              # a soft purple
YOUTUBE = "#FF7A7A"             # a soft red
MOD = "#3DFFB0"
SUB = "#FFB84D"
EVENT = "#FF9A3D"
PLATFORM_COLOURS = {"twitch": TWITCH, "youtube": YOUTUBE}


def stamp(when):
    """HH:MM for a wall-clock time ('' if it is not a time)."""
    try:
        return time.strftime("%H:%M", time.localtime(float(when)))
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def name_badges(line):
    """The little marks after a name: 'mod', 'sub' or both (the streamer gets 'host')."""
    marks = []
    if getattr(line, "owner", False):
        marks.append("host")
    if getattr(line, "mod", False):
        marks.append("mod")
    if getattr(line, "sub", False):
        marks.append("sub")
    return marks


def pieces(line, show_time=True):
    """One feed line -> [(tag, text), ...] in the order they are drawn. The window only has to map tags to colours."""
    out = []
    if show_time:
        out.append(("time", stamp(line.when) + " "))
    platform = line.platform if line.platform in PLATFORM_COLOURS else ""
    out.append(("p_" + (platform or "none"), "● "))
    if line.kind == "event":
        out.append(("event", line.text))
    else:
        out.append(("name_" + (platform or "none"), line.user))
        for mark in name_badges(line):
            out.append(("badge_" + mark, " [%s]" % mark))
        out.append(("text", ": " + line.text))
    return out


def font_size(value):
    """A saved font size -> one of FONT_SIZES (anything else becomes 12)."""
    try:
        size = int(value)
    except (TypeError, ValueError):
        return 12
    return size if size in FONT_SIZES else 12


def step_font(current, direction):
    """The next bigger (+1) or smaller (-1) size, stopping at the ends."""
    sizes = list(FONT_SIZES)
    index = sizes.index(font_size(current))
    return sizes[max(0, min(len(sizes) - 1, index + direction))]


def start_geometry(saved, screen):
    """Where the window opens: where it was last (if still on a screen), else the top right of the main screen."""
    usable = usable_geometry(saved, screen, minimum=MIN_SIZE)
    if usable:
        return usable
    left, top, width, height = screen
    w, h = min(DEFAULT_SIZE[0], width), min(DEFAULT_SIZE[1], height)
    return tk_geometry(w, h, left + max(0, width - w - 24), top + 70)


def resized(width, height, dx, dy, screen_size=None):
    """The new (width, height) after dragging the corner by (dx, dy): never smaller than MIN_SIZE."""
    w, h = max(MIN_SIZE[0], int(width + dx)), max(MIN_SIZE[1], int(height + dy))
    if screen_size:
        w, h = min(w, int(screen_size[0])), min(h, int(screen_size[1]))
    return w, h


def wanted(settings, bridge):
    """True when the window should be on screen: chat is on, the chat reader exists and the switch is on."""
    return bool(settings.get("streaming.enabled", False) and settings.get("streaming.window", True) and bridge is not None)


class ChatWindow:
    def __init__(self, root, settings, bridge_provider):
        self.root = root
        self.settings = settings
        self.bridge_provider = bridge_provider
        self.window = None
        self.text = None
        self.status = None
        self._seq = 0
        self._broken = False
        self._fonts = None
        self._drag = None
        self._styled = False
        self.root.after(TICK_MS, self._tick)

    # ---- the loop ----
    def _tick(self):
        try:
            if not self._broken:
                bridge = self.bridge_provider()
                if wanted(self.settings, bridge):
                    if self.window is None:
                        self._build()
                    self._refresh(bridge)
                elif self.window is not None:
                    self._close_window()
        except Exception:
            log.exception("The chat window failed; it is switched off for this session")
            self._broken = True
            self._close_window()
        try:
            self.root.after(TICK_MS, self._tick)
        except Exception:
            pass

    # ---- building ----
    def _build(self):
        import tkinter as tk
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        window.configure(bg=theme.BORDER_GLOW)
        window.minsize(*MIN_SIZE)
        window.geometry(start_geometry(self.settings.get("streaming.window_geometry", ""), desktop_area(self.root)))
        try:
            window.attributes("-topmost", bool(self.settings.get("streaming.window_top", True)))
        except Exception:
            pass
        inner = tk.Frame(window, bg=theme.BG)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        bar = tk.Frame(inner, bg=theme.SIDEBAR, height=30)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        # The buttons are packed FIRST, so in a narrow window it is the title and status that get squeezed, never the X.
        for text, command in (("✕", self._close_by_user), ("Top", self._toggle_top), ("A+", lambda: self._bump(1)), ("A−", lambda: self._bump(-1))):
            is_close = text == "✕"
            button = tk.Label(bar, text=text, bg=theme.SIDEBAR, fg=theme.TEXT if is_close else theme.MUTED,
                              font=(theme.FONT, 12 if is_close else 10, "bold"), padx=10 if is_close else 7, cursor="hand2")
            button.pack(side="right")
            button.bind("<Button-1>", lambda event, c=command: c())
            hover = "#ff5c5c" if is_close else theme.ACCENT_HOVER
            rest = theme.TEXT if is_close else theme.MUTED
            button.bind("<Enter>", lambda event, b=button, h=hover: b.configure(fg=h))
            button.bind("<Leave>", lambda event, b=button, r=rest: b.configure(fg=r))
        title = tk.Label(bar, text="✦  STARLING CHAT", bg=theme.SIDEBAR, fg=theme.ACCENT, font=(theme.HEAD_FONT, 11, "bold"), cursor="fleur")
        title.pack(side="left", padx=(10, 6))
        self.status = tk.Label(bar, text="", bg=theme.SIDEBAR, fg=theme.MUTED, font=(theme.FONT, 9), anchor="w", cursor="fleur")
        self.status.pack(side="left", fill="x", expand=True)
        for grab in (bar, title, self.status):
            grab.bind("<ButtonPress-1>", self._drag_start)
            grab.bind("<B1-Motion>", self._drag_move)
            grab.bind("<ButtonRelease-1>", self._drag_end)

        body = tk.Frame(inner, bg=theme.PANEL)
        body.pack(fill="both", expand=True)
        grip = tk.Label(body, text="◢", bg=theme.PANEL, fg=theme.ACCENT_DIM, font=(theme.FONT, 12), cursor="size_nw_se")
        grip.pack(side="bottom", anchor="e")
        grip.bind("<ButtonPress-1>", self._grip_start)
        grip.bind("<B1-Motion>", self._grip_move)
        grip.bind("<ButtonRelease-1>", self._drag_end)
        self.text = tk.Text(body, bg=theme.PANEL, fg=theme.TEXT, wrap="word", bd=0, highlightthickness=0, padx=8, pady=6,
                            cursor="arrow", spacing1=2, spacing3=2, state="disabled", insertwidth=0, takefocus=0)
        self.text.pack(side="top", fill="both", expand=True)
        self.window = window
        self._fonts = None
        self._seq = 0
        self._styled = False
        self._apply_fonts()
        window.update_idletasks()
        self._no_focus(window)

    @staticmethod
    def _no_focus(window):
        """Windows: clicking the chat window must never pull the keyboard focus out of the game (NOACTIVATE + no taskbar button)."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(window.winfo_id()) or window.winfo_id()
            style = user32.GetWindowLongW(hwnd, -20)
            wanted_style = style | 0x80 | 0x08000000
            if wanted_style != style:
                user32.SetWindowLongW(hwnd, -20, wanted_style)
        except Exception:
            pass

    def _apply_fonts(self):
        size = font_size(self.settings.get("streaming.window_font", 12))
        if self._fonts == size:
            return
        self._fonts = size
        text = self.text
        base = (theme.FONT, size)
        bold = (theme.FONT, size, "bold")
        text.tag_configure("text", foreground=theme.TEXT, font=base)
        text.tag_configure("time", foreground=theme.MUTED, font=(theme.FONT, max(8, size - 3)))
        text.tag_configure("event", foreground=EVENT, font=(theme.FONT, size, "italic"))
        for platform, colour in PLATFORM_COLOURS.items():
            text.tag_configure("p_" + platform, foreground=colour, font=(theme.FONT, max(8, size - 4)))
            text.tag_configure("name_" + platform, foreground=colour, font=bold)
        text.tag_configure("p_none", foreground=theme.MUTED, font=(theme.FONT, max(8, size - 4)))
        text.tag_configure("name_none", foreground=theme.ACCENT, font=bold)
        text.tag_configure("badge_host", foreground=theme.ACCENT, font=(theme.FONT, max(8, size - 3)))
        text.tag_configure("badge_mod", foreground=MOD, font=(theme.FONT, max(8, size - 3)))
        text.tag_configure("badge_sub", foreground=SUB, font=(theme.FONT, max(8, size - 3)))

    # ---- drawing ----
    def _refresh(self, bridge):
        self._apply_fonts()
        try:
            self.status.configure(text=str(bridge.status())[:70])
        except Exception:
            pass
        lines = bridge.feed.since(self._seq)
        if not lines:
            return
        text = self.text
        stick = text.yview()[1] >= 0.995
        text.configure(state="normal")
        for line in lines:
            if text.index("end-1c") != "1.0":
                text.insert("end", "\n")
            for tag, piece in pieces(line):
                text.insert("end", piece, tag)
            self._seq = line.seq
        extra = int(text.index("end-1c").split(".")[0]) - MAX_DRAWN
        if extra > 0:
            text.delete("1.0", "%d.0" % (extra + 1))
        text.configure(state="disabled")
        if stick:
            text.see("end")

    # ---- the little buttons ----
    def _bump(self, direction):
        self.settings.set("streaming.window_font", step_font(self.settings.get("streaming.window_font", 12), direction))
        self.settings.save()

    def _toggle_top(self):
        on = not bool(self.settings.get("streaming.window_top", True))
        self.settings.set("streaming.window_top", on)
        self.settings.save()
        try:
            self.window.attributes("-topmost", on)
        except Exception:
            pass

    def _close_by_user(self):
        self.settings.set("streaming.window", False)
        self.settings.save()
        self._close_window()

    def _close_window(self):
        window, self.window, self.text, self.status = self.window, None, None, None
        if window is not None:
            try:
                window.destroy()
            except Exception:
                pass

    # ---- dragging and resizing ----
    def _drag_start(self, event):
        self._drag = ("move", event.x_root, event.y_root, self.window.winfo_x(), self.window.winfo_y())

    def _drag_move(self, event):
        if self._drag and self._drag[0] == "move":
            _kind, px, py, wx, wy = self._drag
            self.window.geometry("+%d+%d" % (wx + event.x_root - px, wy + event.y_root - py))

    def _grip_start(self, event):
        self._drag = ("size", event.x_root, event.y_root, self.window.winfo_width(), self.window.winfo_height())

    def _grip_move(self, event):
        if self._drag and self._drag[0] == "size":
            _kind, px, py, width, height = self._drag
            w, h = resized(width, height, event.x_root - px, event.y_root - py, (self.root.winfo_screenwidth(), self.root.winfo_screenheight()))
            self.window.geometry("%dx%d" % (w, h))

    def _drag_end(self, event=None):
        self._drag = None
        try:
            self.window.update_idletasks()
            geometry = make_geometry(self.window.winfo_width(), self.window.winfo_height(), self.window.winfo_x(), self.window.winfo_y())
            if parse_geometry(geometry):
                self.settings.set("streaming.window_geometry", geometry)
                self.settings.save()
        except Exception:
            log.debug("Could not save the chat window position", exc_info=True)
