"""What the Home page shows. No window code here, so it is easy to test."""

import time

from core.identity import wake_phrase
from core.ships import ship_name
from collections import deque
from datetime import datetime

SKIP = ("app.", "journal.", "speech.", "voice.", "ask.")


# which heading each event gets in the Recent events list
KIND_BY_NAME = {"FSDJump": "Exploration", "Location": "System", "Docked": "Journal", "Undocked": "Journal", "LoadGame": "Journal",
                "Touchdown": "Ship", "Liftoff": "Ship", "FuelScoop": "Ship", "LandingGear": "Ship", "ShipChange": "Ship",
                "ShieldState": "Ship", "HullDamage": "Ship", "Loadout": "Ship"}
KIND_BY_TAB = {"combat": "Combat", "exploration": "Exploration", "exobiology": "Exobiology", "mining": "Mining",
               "trading": "Trading", "antixeno": "Anti-Xeno"}


def kind_of(name, data=None):
    name = str(name or "")
    if name.startswith("route.") or name.startswith("Route") or "Route" in name:
        return "Navigation"
    if name in KIND_BY_NAME:
        return KIND_BY_NAME[name]
    try:
        from personality import categories
        tab = categories.category_of(name, data or {})
    except Exception:
        tab = None
    return KIND_BY_TAB.get(tab, "Journal")


class EventFeed:
    """Remembers the last few things that happened, for the Home page."""

    def __init__(self, bus=None, size=10):
        self.items = deque(maxlen=size)
        self.kinds = deque(maxlen=size)
        if bus is not None:
            bus.subscribe("*", self.on_event)

    def on_event(self, event):
        if event.name.startswith(SKIP):
            return
        text = event.data.get("summary") or event.name
        self.items.appendleft((datetime.now().strftime("%H:%M"), str(text), event.priority))
        self.kinds.appendleft(kind_of(event.name, event.data))

    def recent(self):
        return list(self.items)

    def recent_with_kind(self):
        """[(time, kind, text, priority)] for the Recent events list."""
        return [(when, kind, text, priority) for (when, text, priority), kind in zip(self.items, self.kinds)]

    def clear(self):
        self.items.clear()
        self.kinds.clear()


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
        hotas = reader.hotas_devices() if hasattr(reader, "hotas_devices") else reader.x52_devices()
        if hotas:
            names = ", ".join(d.name for d in hotas[:2])
            rows.append(("Joystick", "%s found" % names + (" (+%d more)" % (len(hotas) - 2) if len(hotas) > 2 else ""), "good"))

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


# ---------------------------------------------------------------------------------------------
# The Home page (all the numbers and words it shows, worked out here so it can be tested without a window)
# ---------------------------------------------------------------------------------------------
def population_text(count):
    """12400000 -> '12.4 million'."""
    if not isinstance(count, (int, float)) or count <= 0:
        return "Uninhabited" if count == 0 else "-"
    for size, word in ((1e9, "billion"), (1e6, "million"), (1e3, "thousand")):
        if count >= size:
            value = count / size
            return "%s %s" % (("%.1f" % value).rstrip("0").rstrip("."), word)
    return str(int(count))


def elite_date(now=None):
    """The game's calendar is the real date plus 1286 years (24 Jan 2026 is 24 JAN 3312)."""
    now = now or datetime.now()
    try:
        game = now.replace(year=now.year + 1286)
    except ValueError:                                   # 29 February
        game = now.replace(year=now.year + 1286, day=28)
    return game.strftime("%d %b ").upper().lstrip("0") + str(game.year)


def _percent(value, whole):
    if isinstance(value, (int, float)) and isinstance(whole, (int, float)) and whole > 0:
        return max(0.0, min(1.0, float(value) / float(whole)))
    return 0.0


def home_data(app, now=None):
    """Everything the Home page draws, as plain values. Never raises: missing facts become '-' or 0."""
    now = now or datetime.now()
    rows = {label: (text, tone) for label, text, tone in collect_status(app)}
    state = getattr(app, "state", None)

    voice_text, voice_tone = rows.get("Voice", ("Not started", "muted"))
    listening, listen_tone = rows.get("Listening", ("Off", "muted"))
    joystick = rows.get("Joystick")
    game_text, game_tone = rows.get("Game", ("Not watching", "muted"))
    tiles = [
        ("VOICE", "\u25C9", voice_text.upper() if len(voice_text) < 14 else "PROBLEM", voice_tone,
         ("Listening... Say \"%s\"" % _wake(app)) if listen_tone == "good" else ("Listening: %s" % listening)),
        ("HOTAS", "\u2316", "CONNECTED" if joystick else "NOT FOUND", "good" if joystick else "muted",
         joystick[0].replace(" found", "") if joystick else "No joystick seen yet"),
        ("JOURNAL", "\u25A4", "WATCHING" if game_tone == "good" else "NOT WATCHING", game_tone,
         "Game events active" if getattr(state, "status_seen", False) else "Waiting for the game"),
    ]

    def get(name, default=None):
        return getattr(state, name, default) if state is not None else default

    hull = get("hull_health", 1.0)
    shields = 1.0 if get("shields_up", True) else 0.0
    cargo, capacity = get("cargo_tons"), get("cargo_capacity")
    if isinstance(cargo, (int, float)) and isinstance(capacity, (int, float)) and capacity > 0:
        cargo_text = "%d / %d T" % (round(cargo), round(capacity))
    elif isinstance(cargo, (int, float)):
        cargo_text = "%d T" % round(cargo)
    else:
        cargo_text = "-"
    fuel = _percent(get("fuel_main"), get("fuel_capacity"))
    system = get("system") or "-"
    model = get("ship_model") or (ship_name(get("ship")) if get("ship") else "") or ""
    custom = get("ship_name") or ""
    ship = custom or model or "-"
    where = "Docked" if get("docked") else ("Supercruise" if get("in_supercruise") else "In flight")
    mood_text = ""
    mood = getattr(app, "mood", None)
    try:
        if mood is not None and app.settings.get("personality.mood_mode", "auto") != "fixed":
            mood_text = mood.describe()
        else:
            mood_text = str(app.settings.get("personality.mood", "Friendly"))
    except Exception:
        mood_text = ""
    commander = get("commander") or ""
    return {
        "tiles": tiles,
        "commander": ("CMDR " + commander.upper()) if commander else "COMMANDER",
        "header_system": system.upper() if system != "-" else "",
        "time": now.strftime("%H:%M"), "date": elite_date(now),
        "system": {"name": system, "security": get("system_security") or "-", "allegiance": get("system_allegiance") or "-",
                   "population": population_text(get("system_population"))},
        "ship": {"name": ship, "model": model, "code": get("ship") or "", "fuel": fuel, "hull": max(0.0, min(1.0, float(hull or 0))), "shields": shields,
                 "cargo": _percent(cargo, capacity), "cargo_text": cargo_text, "where": "%s  |  %s" % (system, where)},
        "mood": mood_text,
    }


def _wake(app):
    try:
        return wake_phrase(app.settings)
    except Exception:
        return "Starling"


def mic_state(app):
    """(words, tone) for the microphone box at the top of the window: is she listening to me right now?"""
    listener = getattr(app, "listener", None)
    if listener is None:
        return "MIC OFF", "muted"
    if getattr(listener, "failed_reason", None):
        return "MIC PROBLEM", "bad"
    ready = getattr(listener, "ready", None)
    if ready is not None and not ready.is_set():
        return "MIC STARTING", "warn"
    ptt = getattr(app, "ptt", None)
    try:
        mode = app.settings.get("ptt.mode", "off")
        if mode != "off" and ptt is not None:
            return ("LISTENING", "good") if ptt.is_open() else ("PUSH TO TALK", "muted")
    except Exception:
        pass
    return "LISTENING", "good"


def header_data(app, now=None):
    """The small words at the top right of the window (cheap: it runs every second on every page)."""
    now = now or datetime.now()
    state = getattr(app, "state", None)
    commander = getattr(state, "commander", None) if state is not None else None
    system = getattr(state, "system", None) if state is not None else None
    return {"commander": ("CMDR " + str(commander).upper()) if commander else "COMMANDER",
            "system": str(system).upper() if system else "", "time": now.strftime("%H:%M"), "date": elite_date(now),
            "mic": mic_state(app)}
