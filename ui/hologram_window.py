"""
Her hologram on screen (the tkinter part). What she looks like is decided in ui/hologram.py (plain Python, tested);
this file only shows the pixels in a see-through, click-through window and lets you drag her to where you want her.

  * Settings > Personality: "Show her as a hologram on the dash" (off until you switch it on), size, mouth opening.
  * "Move her" on the Personality page: she can be dragged (a thin frame appears); double-click, or wait 90 seconds, to lock her again.
    Where you drop her is remembered.
  * The game must be in Borderless or Windowed mode, like the route map.
  * If anything goes wrong the hologram switches itself off for the session and says why in the log. It never touches the game.
"""

import re
import time

from core.logger import get_logger
from ui import game_watch, hologram, screens

log = get_logger("hologram_window")

IDLE_MS = 450            # while she is hidden: just check now and then
SHOWN_MS = 100           # while she is shown: ten pictures a second
TALKING_MS = 66          # while she speaks: fifteen
MOVE_SECONDS = 90
TEST_SECONDS = 10
PPOSE_TEST_SECONDS = 80
SALUTE_AFTER_LOAD = 12.0         # seconds after the game loads, so her greeting has finished first
SALUTE_WORDS = re.compile(r"\b(o7|o 7|oh seven|o seven|salute)\b", re.IGNORECASE)
TEST_LINE = "Commander, this is how I will look on your dash. Gear down and nice and easy."


def set_click_through(window, on):
    """Windows: let the mouse pass straight through to the game (on) or catch it so she can be dragged (off)."""
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        GWL_EXSTYLE, LAYERED, TRANSPARENT, TOOLWINDOW, NOACTIVATE = -20, 0x80000, 0x20, 0x80, 0x08000000
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | LAYERED | TOOLWINDOW
        style = (style | TRANSPARENT | NOACTIVATE) if on else (style & ~TRANSPARENT & ~NOACTIVATE)
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    except Exception:
        pass            # not Windows: it still works, it just takes mouse clicks


BOOT_SECONDS = 20.0      # after the game window first appears she waits this long, then powers up ("getting herself together")


def foreground_title():
    """The title of the window you are in right now, or None when that cannot be found (not Windows)."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        handle = user32.GetForegroundWindow()
        if not handle:
            return ""
        length = user32.GetWindowTextLengthW(handle)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(handle, buffer, length + 1)
        return buffer.value
    except Exception:
        return None


class HologramFeed:
    """Where the hologram gets its facts from: the app's events, screen focus, microphone and brain."""

    def __init__(self, app, hologram_getter):
        self.app = app
        self.get = hologram_getter          # () -> the current Hologram (it is rebuilt when the size changes)
        self._attached = False
        self.pending = ""
        self.waiting_timeline = None   # timing that arrived before the sound started
        self.waiting_length = None
        self.title_provider = foreground_title
        self.boot_seconds = BOOT_SECONDS
        self._focus_at = 0.0
        self._focus = True
        self._booted_from = None       # when the game window first came into focus
        self.game_in_front = None      # True / False from the window title, None when it cannot be read

    def game_in_focus(self, now):
        """True when Elite is the window you are in AND she has finished starting up. Checked twice a second at most.
        Where the window cannot be read she stays on (she only follows the in-game screens then)."""
        if now - self._focus_at < 0.5:
            return self._focus
        self._focus_at = now
        try:
            title = self.title_provider()
        except Exception:
            title = None
        if title is None:
            self._focus = True
            self.game_in_front = None
            return True
        from control.sender import _is_game
        self.game_in_front = bool(_is_game(title))
        if self.game_in_front:
            if self._booted_from is None:
                self._booted_from = now
            self._focus = now - self._booted_from >= self.boot_seconds
        else:
            self._focus = False
        return self._focus

    def game_gone(self):
        """Forget the start-up wait when the game has closed, so the next start gets a fresh one."""
        self._booted_from = None

    def attach(self):
        bus = getattr(self.app, "bus", None)
        if bus is None or self._attached:
            return
        bus.subscribe("speech.started", self._started)
        bus.subscribe("speech.audio", self._audio)
        bus.subscribe("speech.finished", self._finished)
        bus.subscribe("voice.heard", self._heard)
        bus.subscribe("LoadGame", self._game_loaded)
        for name in hologram.REACTIONS:                    # game events she may react to with a nod, a shake of the head, a startle...
            bus.subscribe(name, self._reacted)
        self._attached = True

    def _started(self, event):
        """The line was handed to the voice. Her lips wait for the real sound (speech.audio), because making the sound takes a moment.
        A recorded line has no such signal, so it starts at once."""
        try:
            self.pending = event.data.get("text", "")
            if event.data.get("audio"):
                holo = self.get()
                if holo is not None:
                    holo.speech_started(self.pending)
        except Exception:
            log.exception("The hologram could not follow what she said")

    def _audio(self, event):
        try:
            holo = self.get()
            if holo is None:
                return
            what = event.data.get("what")
            if what == "start":
                holo.speech_started(event.data.get("text") or self.pending)
                if self.waiting_timeline:                            # the exact timing was ready before the sound started
                    holo.set_timeline(self.waiting_timeline)
                if self.waiting_length:
                    holo.set_duration(self.waiting_length)
                self.waiting_timeline, self.waiting_length = None, None
            elif what == "timeline":
                if holo.speaking:
                    holo.set_timeline(event.data.get("seconds") or [])
                else:
                    self.waiting_timeline = event.data.get("seconds") or None
            elif what == "length":
                if holo.speaking:
                    holo.set_duration(event.data.get("seconds"))
                else:
                    self.waiting_length = event.data.get("seconds")
            elif what == "end":
                holo.speech_finished()
                self.waiting_timeline, self.waiting_length = None, None
        except Exception:
            log.exception("The hologram could not follow the sound")

    def _finished(self, event):
        try:
            holo = self.get()
            if holo is not None:
                holo.speech_finished()
        except Exception:
            log.exception("The hologram could not follow the end of a line")

    def _reacted(self, event):
        try:
            holo = self.get()
            if holo is not None and self.app.settings.get("hologram.reactions", True):
                holo.react_to(getattr(event, "name", ""))
        except Exception:
            log.exception("The hologram could not react to a game event")

    def _game_loaded(self, event):
        """The game just loaded: once her greeting is done she gives you a salute."""
        try:
            holo = self.get()
            if holo is not None:
                holo.salute(delay=SALUTE_AFTER_LOAD)
        except Exception:
            log.exception("The hologram could not get ready to salute")

    def _heard(self, event):
        try:
            data = event.data
            said = " ".join(str(data.get(k) or "") for k in ("command", "text"))
            if SALUTE_WORDS.search(said):
                holo = self.get()
                if holo is not None:
                    holo.salute()                    # "o7" or "salute": she salutes back
            if data.get("wake") and not (data.get("command") or "").strip():
                holo = self.get()
                if holo is not None and self.app.settings.get("hologram.listening_colour", True):
                    holo.heard_her_name()           # her name on its own: she is waiting for the rest
        except Exception:
            log.exception("The hologram could not follow her name being heard")

    def pull_levels(self, holo):
        """Hands the hologram the loudness of the sound that is playing (from the speech manager), so its mouth opens and closes with it."""
        speech = getattr(self.app, "speech", None)
        taker = getattr(speech, "take_levels", None)
        if taker is None or holo is None:
            return
        try:
            taken = taker()
            if taken:
                holo.add_levels(taken)
        except Exception:
            log.debug("Could not read the sound levels", exc_info=True)

    def gui_focus(self):
        return int(getattr(getattr(self.app, "state", None), "gui_focus", 0) or 0)

    def in_world(self):
        """True when Status.json shows a ship, SRV, fighter or on-foot switch. The main menu and the loading screens show none."""
        state = getattr(self.app, "state", None)
        return bool(getattr(state, "in_world", False)) and not bool(getattr(state, "at_main_menu", False))

    def game_quit(self):
        """True when the game looks closed. The journal's idea of that can be wrong (Starling started while you sat still in a station, so
        Status.json was old), so seeing the Elite window in front overrules it."""
        quit_flag = bool(getattr(getattr(self.app, "state", None), "game_quit", False))
        if quit_flag:
            import time as _time
            self.game_in_focus(_time.monotonic())
            if self.game_in_front:
                return False
        return quit_flag

    def listening(self):
        """Green: push-to-talk is held open, or she has asked you a question and is waiting. Never just because the microphone is open."""
        if not self.app.settings.get("hologram.listening_colour", True):
            return False
        ptt = getattr(self.app, "ptt", None)
        try:
            if ptt is not None and ptt.enabled() and ptt.is_open():
                return True
        except Exception:
            pass
        ask = getattr(self.app, "ask", None)
        pending = getattr(ask, "pending", None) if ask is not None else None
        return bool(pending and pending.get("open"))

    def thinking(self):
        if not self.app.settings.get("hologram.thinking_colour", True):
            return False
        brain = getattr(self.app, "brain", None)
        return bool(brain is not None and getattr(brain, "thinking", 0) > 0)


class HologramWindow:
    def __init__(self, root, settings, feed_factory):
        self.root = root
        self.settings = settings
        self.feed = feed_factory(self.current)
        self.holo = None
        self.window = None
        self.canvas = None
        self.photo = None
        self.item = None
        self.test_until = 0.0
        self.moving_until = 0.0
        self._height = 0
        self._rect = None
        self._rect_at = 0.0
        self._broken = False
        self._shown = False
        self._drag = None
        self._geometry = None
        self._tk_ready = None
        try:
            self.feed.attach()
        except Exception:
            log.exception("The hologram could not listen for events")
        self.root.after(IDLE_MS, self._tick)

    # ---- for the dashboard ----
    def current(self):
        return self.holo

    def show_test(self, seconds=TEST_SECONDS):
        self.test_until = time.monotonic() + seconds
        if self.holo is not None:
            self.holo.speech_started(TEST_LINE)

    def test_poses(self):
        """Shows her and plays every pose clip once, one after another (about 35 seconds), whatever the game is doing."""
        self.test_until = time.monotonic() + POSE_TEST_SECONDS
        self.pose_queue = ["thinking", "listening", "pleased", "salute", "bored1", "bored2", "nod", "shake", "tilt", "glance_left", "glance_right", "startle"]
        if self.holo is not None:
            self.holo.stop_clip(fast=True)

    def _pose_test_step(self, holo, now):
        """Starts the next clip of the test when the one before has finished (a clip that is still loading is simply asked again next tick)."""
        queue = getattr(self, "pose_queue", None)
        if not queue or holo.clip is not None or holo.clip_mix > 0.05 or holo.speaking or holo.g_name:
            return
        if queue[0] in hologram.GESTURES:
            holo.poses_on = True                                        # (a test must work even with the poses switched off)
            if holo.gesture(queue[0], now):
                queue.pop(0)
        elif holo.start_clip(queue[0], now, forced=True):
            queue.pop(0)

    def start_move(self, seconds=MOVE_SECONDS):
        self.moving_until = time.monotonic() + seconds

    def stop_move(self):
        self.moving_until = 0.0

    def moving(self):
        return time.monotonic() < self.moving_until

    # ---- the loop ----
    def _tick(self):
        delay = IDLE_MS
        try:
            if not self._broken:
                delay = self._update()
        except Exception:
            log.exception("The hologram failed; it is switched off for this session")
            self._broken = True
            self._hide()
        try:
            self.root.after(delay, self._tick)
        except Exception:
            pass

    def _screen_rect(self):
        now = time.monotonic()
        if self._rect is None or now - self._rect_at > 5.0:
            main = (self.root.winfo_screenwidth(), self.root.winfo_screenheight())
            self._rect = screens.overlay_rect(self.settings.get("overlay.screen", "auto"), main)
            self._rect_at = now
        return self._rect

    def _why(self, now, hidden_reason):
        """Writes one log line each time the reason she is (not) shown changes, so a missing hologram can be explained from the log."""
        if hidden_reason != getattr(self, "_last_reason", None):
            self._last_reason = hidden_reason
            log.info("Hologram: %s", hidden_reason or "shown")

    def wanted(self, now):
        s = self.settings
        if (self.feed.game_quit() or game_watch.game_closed()) and not self.moving() and now >= self.test_until:
            return False
        return bool(s.get("hologram.enabled", False)) or now < self.test_until or self.moving()

    def _ensure(self, screen_h):
        height = hologram.height_for(screen_h, self.settings.get("hologram.size", 100))
        if self.holo is not None and height == self._height:
            return
        old = self.holo
        assets = hologram.Assets(height)
        self.holo = hologram.Hologram(assets)
        if old is not None:                           # keep her colours and power across a resize
            self.holo.mix, self.holo.power = old.mix, old.power
        self._height = height
        self.photo = None
        self._geometry = None

    def _update(self):
        now = time.monotonic()
        if not self.wanted(now):
            if not self.settings.get("hologram.enabled", False):
                self._why(now, "off in settings")
            elif self.feed.game_quit():
                self._why(now, "hidden: the game is not running and Elite is not in front. The 'Show her hologram for 10 seconds' button still shows her")
            if self._shown and self.holo is not None:
                powered_down = self.holo.tick(powered=False)
                if powered_down <= 0.03:
                    self._hide()
                else:
                    self._draw(now)
                    return SHOWN_MS
            elif self._shown:
                self._hide()
            return IDLE_MS
        ox, oy, sw, sh = self._screen_rect()
        self._ensure(sh)
        holo = self.holo
        s = self.settings
        holo.open_fraction = max(0.2, min(1.0, float(s.get("hologram.mouth_open", 55)) / 100.0))
        holo.flicker_on = bool(s.get("hologram.flicker", True))
        holo.fx_beam = bool(s.get("hologram.sparks", True))
        holo.fx_turn = bool(s.get("hologram.turn", True))
        holo.idle_on = bool(s.get("hologram.idle_loop", True))
        holo.poses_on = bool(s.get("hologram.poses", True))
        holo.talk_motion = bool(s.get("hologram.talk_motion", True))
        if holo.poses_on and not getattr(holo, "clips_preloaded", False):
            holo.clips_preloaded = True
            holo.preload_clips()                      # thinking and listening load in the background so they are ready when needed
        holo.moving = self.moving()
        testing = now < self.test_until
        focus = self.feed.gui_focus()
        if self.feed.game_quit():
            self.feed.game_gone()
        self.feed.pull_levels(holo)
        in_game = self.feed.game_in_focus(now)
        waiting = bool(s.get("hologram.cockpit_only", True)) and not self.feed.in_world()
        shown_ok = (focus == 0 and in_game and not waiting)
        keep_on = testing or holo.moving or not s.get("hologram.power_down", True)
        if not s.get("hologram.power_down", True) and waiting and not (testing or holo.moving):
            keep_on = False                       # the menu rule still applies when she does not power down on other screens
        self._why(now, None if (keep_on or shown_ok)
                  else ("powered down: Elite is not the window in front (or still starting up)" if not in_game
                        else "waiting: you are at the main menu or a loading screen (no cockpit yet)" if waiting
                        else "powered down: a game screen is open (GuiFocus %d)" % focus))
        powered = keep_on or shown_ok
        self._pose_test_step(holo, now)
        visible = holo.tick(listening=self.feed.listening(), thinking=self.feed.thinking(), powered=powered)
        if visible <= 0.03 and not holo.speaking:
            if self._shown:
                self._hide()
            return IDLE_MS
        self._draw(now)
        return TALKING_MS if holo.speaking else SHOWN_MS

    # ---- the window ----
    def _make_window(self):
        import tkinter as tk
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.configure(bg=hologram.KEY_HEX)
        try:
            window.attributes("-transparentcolor", hologram.KEY_HEX)
        except Exception:
            pass
        canvas = tk.Canvas(window, bg=hologram.KEY_HEX, highlightthickness=0, bd=0)
        canvas.pack(fill="both", expand=True)
        self.window, self.canvas = window, canvas
        window.update_idletasks()
        set_click_through(window, True)
        self._click_through_on = True
        canvas.bind("<ButtonPress-1>", self._drag_start)
        canvas.bind("<B1-Motion>", self._drag_move)
        canvas.bind("<ButtonRelease-1>", self._drag_end)
        canvas.bind("<Double-Button-1>", lambda event: self.stop_move())

    def _hide(self):
        self._shown = False
        if self.window is not None:
            try:
                self.window.withdraw()
            except Exception:
                pass

    def _draw(self, now):
        from PIL import Image, ImageTk
        if self.window is None:
            self._make_window()
        holo = self.holo
        a = holo.assets
        pixels = holo.render()
        image = Image.fromarray(pixels, "RGB")
        if self.photo is None:
            self.photo = ImageTk.PhotoImage(image)
            self.canvas.configure(width=a.window_w, height=a.window_h)
            if self.item is not None:
                self.canvas.delete(self.item)
            self.item = self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        else:
            self.photo.paste(image)
        moving = holo.moving
        want_through = not moving
        if want_through != getattr(self, "_click_through_on", True):
            set_click_through(self.window, want_through)
            self._click_through_on = want_through
        if not moving or self._drag is None:
            self._place(a)
        if not self._shown:
            self.window.deiconify()
            self.window.attributes("-topmost", True)
            self._shown = True
        else:
            self.window.lift()

    def _place(self, a):
        ox, oy, sw, sh = self._screen_rect()
        # her PICTURE sits where the settings say; the window is wider by the room beside her (for the salute arm), so it starts further left
        x, y = hologram.window_position(sw, sh, a.width, a.window_h, self.settings.get("hologram.left", 6.5),
                                        self.settings.get("hologram.bottom", 24.0))
        geometry = "%dx%d+%d+%d" % (a.window_w, a.window_h, ox + x - a.pad_left, oy + y)
        if geometry != self._geometry:
            self._geometry = geometry
            self.window.geometry(geometry)

    # ---- dragging (only while "Move her" is on) ----
    def _drag_start(self, event):
        if not self.moving():
            return
        self._drag = (event.x_root - self.window.winfo_x(), event.y_root - self.window.winfo_y())

    def _drag_move(self, event):
        if self._drag is None or not self.moving():
            return
        x, y = event.x_root - self._drag[0], event.y_root - self._drag[1]
        self.window.geometry("+%d+%d" % (x, y))

    def _drag_end(self, event):
        if self._drag is None:
            return
        self._drag = None
        try:
            ox, oy, sw, sh = self._screen_rect()
            a = self.holo.assets
            left, bottom = hologram.percents_from_position(sw, sh, a.width, a.window_h,
                                                           self.window.winfo_x() - ox + a.pad_left, self.window.winfo_y() - oy)
            self.settings.set("hologram.left", left)
            self.settings.set("hologram.bottom", bottom)
            self.settings.save()
            self._geometry = None
        except Exception:
            log.exception("Could not remember where she was dropped")
