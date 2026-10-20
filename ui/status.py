"""What the Home page shows. No window code here, so it is easy to test."""

import time

from core.identity import wake_phrase
from core.ships import ship_name
from collections import deque
from datetime import datetime

SKIP = ("app.", "journal.", "speech.", "voice.", "ask.")


class EventFeed:
    """Remembers the last few things that happened, for the Home page."""

    def __init__(self, bus=None, size=10):
        self.items = deque(maxlen=size)
        if bus is not None:
            bus.subscribe("*", self.on_event)

    def on_event(self, event):
        if event.name.startswith(SKIP):
            return
        text = event.data.get("summary") or event.name
        self.items.appendleft((datetime.now().strftime("%H:%M"), str(text), event.priority))

    def recent(self):
        return list(self.items)


def collect_status(app):
    """A snapshot of how STARLING is doing, as plain words: [(label, text, 'good'|'warn'|'bad'|'muted')]."""
    rows = []

    # voice
    kokoro = app.providers.get("kokoro") if app.providers else None
    if not app.settings.get("speech.enabled", True):
        rows.append(("Voice", "Switched off", "muted"))
    elif kokoro is None:
        rows.append(("Voice", "Not started", "muted"))
    elif kokoro.ready.is_set():
        rows.append(("Voice", "Ready", "good"))
    elif kokoro.failed_reason:
        rows.append(("Voice", "Problem: " + kokoro.failed_reason, "bad"))
    else:
        rows.append(("Voice", "Loading...", "warn"))

    # listening
    listener = app.listener
    if listener is None:
        rows.append(("Listening", "Off", "muted"))
    elif listener.failed_reason:
        rows.append(("Listening", "Problem: " + listener.failed_reason, "bad"))
    elif listener.ready.is_set():
        rows.append(("Listening", "On - say \"%s\"" % wake_phrase(app.settings), "good"))
    else:
        rows.append(("Listening", "Starting...", "warn"))

    # push-to-talk and joystick
    ptt = getattr(app, "ptt", None)
    mode = app.settings.get("ptt.mode", "off")
    if mode == "off":
        rows.append(("Push-to-talk", "Off", "muted"))
    elif not app.settings.get("ptt.button", ""):
        rows.append(("Push-to-talk", "No button chosen yet (Controls page)", "warn"))
    elif ptt is None:
        rows.append(("Push-to-talk", "Starts when listening starts", "muted"))
    else:
        rows.append(("Push-to-talk", "%s - microphone %s" % (mode, "OPEN" if ptt.is_open() else "closed"),
                     "good" if ptt.is_open() else "muted"))
    reader = getattr(app, "buttons", None)
    if reader is not None:
        x52 = reader.x52_devices()
        if x52:
            rows.append(("Joystick", "%s found" % x52[0].name, "good"))

    # game
    if app.monitor is None:
        rows.append(("Game", "Not watching", "muted"))
    else:
        rows.append(("Game", "Watching the journal", "good"))

    state = app.state
    if state is not None:
        if state.commander:
            rows.append(("Commander", str(state.commander), "muted"))
        where = state.system or "-"
        rows.append(("System", where, "muted"))
        if state.ship:
            rows.append(("Ship", str(state.ship_name or ship_name(state.ship)), "muted"))
        carried = state.exobiology.carried_total() if state.exobiology else 0
        if carried:
            from journal.exobiology import spoken_credits
            rows.append(("Exobiology on board", "about %s credits" % spoken_credits(carried), "muted"))

    mood = getattr(app, "mood", None)
    if app.settings.get("personality.mood_mode", "auto") == "fixed" or mood is None:
        rows.append(("Mood", str(app.settings.get("personality.mood", "Friendly")) + " (fixed)", "muted"))
    else:
        rows.append(("Mood", mood.describe(), "muted"))
        if mood.history:
            _when, label, change = mood.history[0]
            rows.append(("Last mood change", "%s (%+.1f)" % (label, change), "good" if change > 0 else "bad"))
    return rows
