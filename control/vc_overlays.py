"""
THE VOID COMPASS OVERLAYS - what you can call each one by voice.

Void Compass (a separate app) draws overlays over the game. Starling switches them on and off through
Void Compass's own Local API, so no keys are pressed and Elite does not need to be in front.

Each entry:  (Void Compass id,  how she says it,  [names you can use],  needs_word)
  needs_word=True  means you must say "overlay" or "HUD" too ("show the navigation overlay"),
                   because the bare name also means something in the ship ("navigation" is a panel).
Add a new overlay here if Void Compass gets one: nothing else needs touching.
"""

OVERLAYS = [
    ("navigation", "the navigation overlay", ["navigation", "nav", "compass"], True),
    ("survey", "the survey overlay", ["survey", "survey operations", "exploration"], True),
    ("heartbeat", "the heartbeat overlay", ["heartbeat", "journal heartbeat", "watcher", "the watcher"], False),
    ("toast", "the notifications overlay", ["notifications", "cockpit notifications", "notification", "popups", "pop ups"], True),
    ("achievements", "the achievements overlay", ["achievements", "achievement"], False),
    ("cargo", "the cargo overlay", ["cargo", "cargo manifest"], True),
    ("carrier", "the carrier overlay", ["carrier", "fleet carrier", "squadron carrier", "fleet"], True),
    ("prospector", "the prospector overlay", ["prospector", "prospector analysis", "mining"], True),
    ("planet-materials", "the planet materials overlay", ["planet materials", "materials", "planetary materials"], True),
    ("powerplay", "the powerplay overlay", ["powerplay", "powerplay operations", "power play"], False),
    ("gravity", "the gravity warning", ["gravity", "gravity warning"], True),
    ("station", "the station overlay", ["station", "station information", "station info"], True),
    ("galnet-ticker", "the galnet ticker", ["galnet", "galnet ticker", "news ticker", "news"], True),
    ("music-player", "the music player", ["music", "music player"], True),
    ("contact-scope", "the contact scope", ["contact scope", "deep space contacts", "deep space contact scope", "contacts scope", "deep space scope"], False),
    ("jump-info", "the jump info overlay", ["jump info", "jump information"], False),
    ("colony-needs", "the construction needs overlay", ["construction needs", "colony needs", "colonisation needs", "construction"], True),
    ("trade-route", "the trade route overlay", ["trade route", "trade routes", "trading"], True),
    ("galaxy-minimap", "the galaxy minimap", ["galaxy minimap", "mini map", "minimap", "galaxy mini map"], False),
    ("postcards", "the postcards overlay", ["postcards", "postcard", "screenshots polaroid"], True),
    ("ground-target", "the planet waypoint overlay", ["planet waypoint", "planet waypoint navigation", "waypoint navigation", "surface navigation", "ground navigation", "surface nav"], False),
]

# "hide all overlays" / "show all overlays". The special targets are handled in control/runner.py.
HIDE_ALL = "*hide"
SHOW_ALL = "*show"


def discover(rows, known=None):
    """New overlays Void Compass reports that we have no entry for.

    rows  = the "overlays" list from Void Compass ([{"id": "...", "name": "..."}]).
    Returns [(id, label, [names], needs_word)] in the same shape as OVERLAYS, so a Void Compass update that adds
    an overlay is usable by voice straight away, with no change to Starling.
    """
    import re
    known_ids = {row[0] for row in (known if known is not None else OVERLAYS)}
    found = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        overlay_id = str(row.get("id") or "").strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,40}", overlay_id) or overlay_id in known_ids:
            continue
        name = re.sub(r"[^a-z0-9 ]+", " ", str(row.get("name") or overlay_id.replace("-", " ")).lower())
        name = re.sub(r"\b(overlay|hud)\b", " ", name)
        name = " ".join(name.split()) or overlay_id.replace("-", " ")
        names = [name]
        plain = overlay_id.replace("-", " ").replace("_", " ")
        if plain != name:
            names.append(plain)
        found.append((overlay_id, "the %s overlay" % name, names, True))
    return found
