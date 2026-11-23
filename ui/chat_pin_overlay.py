"""The comment on the screen (streaming/pin.py): a coloured name tag over a dark bar with the chatter's words, like a YouTube
"highlighted comment". One see-through, click-through window built like the red alert banner and the hack panel
(ui/red_alert_overlay.py): it never takes the mouse or the keyboard focus from the game. Needs Elite in Borderless or Windowed mode.
Settings: streaming.pin_overlay (on/off), streaming.pin_x / pin_up (drag the box on the Overlays page), streaming.pin_size, streaming.pin_obs (a window OBS can pick)."""
import time

from core.logger import get_logger
from ui.red_alert_overlay import RedAlertOverlay

log = get_logger("chat_pin_overlay")

IDLE_MS = 400
TAG_COLOURS = {"twitch": "#9146FF", "youtube": "#F5A623"}
DEFAULT_TAG = "#F5A623"
BAR = "#14171C"
TEXT = "#FFFFFF"
TAG_TEXT = "#FFFFFF"
WIDTH_SHARE = {"Small": 0.26, "Medium": 0.34, "Large": 0.44}
OBS_TITLE = "Starling Comment"


def wrap(text, measure, width, max_lines=5):
    """Cuts text into lines no wider than 'width' pixels (measure(text) -> pixels). At most max_lines; the last one ends with ... if cut."""
    words = str(text or "").split()
    lines, line = [], ""
    for word in words:
        trial = (line + " " + word).strip()
        if measure(trial) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" .,;:") + "…"
    return lines


def gaps(settings):
    """(gap from the left, gap from the bottom) in percent of the screen: where you dragged the box on the Overlays page."""
    out = []
    for key, default in (("streaming.pin_x", 2.0), ("streaming.pin_up", 8.0)):
        try:
            out.append(min(95.0, max(0.0, float(settings.get(key, default)))))
        except (TypeError, ValueError):
            out.append(default)
    return tuple(out)


def place(screen_w, screen_h, width, height, gap_x, gap_up):
    """The window's top left inside the screen: gap_x percent from the left edge, gap_up percent up from the bottom edge, kept on screen."""
    left = int(screen_w * gap_x / 100.0)
    top = int(screen_h - screen_h * gap_up / 100.0 - height)
    return max(0, min(left, screen_w - width)), max(0, min(top, screen_h - height))


def tag_colour(platform):
    return TAG_COLOURS.get(str(platform or ""), DEFAULT_TAG)


class ChatPinOverlay(RedAlertOverlay):
    def __init__(self, root, settings, pin_provider, speech_provider=None):
        self.pin_provider = pin_provider
        self.speech_provider = speech_provider
        self._drawn = None
        super().__init__(root, settings, active_provider=lambda: self._current() is not None)

    def _pin(self):
        try:
            return self.pin_provider()
        except Exception:
            return None

    def _current(self):
        pin = self._pin()
        if pin is None or not self.settings.get("streaming.pin_overlay", True):
            return None
        return pin.current()

    def _speaking(self):
        try:
            speech = self.speech_provider() if self.speech_provider else None
            return bool(speech is not None and speech.is_busy())
        except Exception:
            return False

    def _tick(self):
        try:
            if not self._broken:
                pin = self._pin()
                if pin is not None:
                    pin.settle(self._speaking())
                if self._current() is not None:
                    self._show()
                elif self._shown:
                    self._hide()
        except Exception:
            log.exception("The pinned comment overlay failed; it is switched off for this session")
            self._broken = True
            self._hide()
        try:
            self.root.after(IDLE_MS, self._tick)
        except Exception:
            pass

    def _harden(self, window):
        super()._harden(window)
        if self.settings.get("streaming.pin_obs", False):
            try:
                from ui.hologram_window import set_click_through
                set_click_through(window, True, True, title=OBS_TITLE)
            except Exception:
                pass

    def _show(self):
        import tkinter.font as tkfont
        current = self._current()
        if current is None:
            return
        user, text, platform = current
        x, y, w, h = self._screen_rect()
        gap_x, gap_up = gaps(self.settings)
        size = str(self.settings.get("streaming.pin_size", "Medium"))
        key = (current, gap_x, gap_up, size, x, y, w, h)
        first = self.window is None
        if first:
            self.window = self._make()
        if key != self._drawn or first:
            self._drawn = key
            width = int(w * WIDTH_SHARE.get(size, WIDTH_SHARE["Medium"]))
            pixel = max(14, int(width * 0.050))
            body = tkfont.Font(family="Segoe UI", size=-pixel, weight="bold")
            name = tkfont.Font(family="Segoe UI", size=-int(pixel * 0.95), weight="bold")
            pad = int(pixel * 0.6)
            lines = wrap(text, body.measure, width - pad * 2)
            line_h = int(pixel * 1.35)
            tag_h = int(pixel * 1.6)
            tag_w = min(width, name.measure(user) + pad * 2)
            height = tag_h + pad * 2 + line_h * len(lines)
            self.canvas.delete("all")
            self.canvas.configure(width=width, height=height)
            self.canvas.create_rectangle(0, tag_h, width, height, fill=BAR, outline="")
            self.canvas.create_rectangle(0, 0, tag_w, tag_h, fill=tag_colour(platform), outline="")
            self.canvas.create_text(pad, tag_h // 2, text=user, fill=TAG_TEXT, font=name, anchor="w")
            for index, line in enumerate(lines):
                self.canvas.create_text(pad, tag_h + pad + line_h * index + line_h // 2, text=line, fill=TEXT, font=body, anchor="w")
            left, top = place(w, h, width, height, gap_x, gap_up)
            self.window.geometry("%dx%d+%d+%d" % (width, height, x + left, y + top))
            self._font = (body, name)
        if not self._shown:
            self.window.deiconify()
            log.info("Pinned comment shown")
        self.window.attributes("-topmost", True)
        self.window.lift()
        self._harden(self.window)
        self._put_on_top_without_focus(self.window)
        self._shown = True
