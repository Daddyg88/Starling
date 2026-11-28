"""
One shared rule for the overlays: they only show while Elite is the window you are in, like the hologram.

When you alt-tab to something else (the browser, OBS, Starling's own window) the biology list, route map, red alert banner,
settlement map and hack panel go away, and they come back when Elite is in front again. The test buttons still show them.
Where the window in front cannot be read (not Windows) nothing is hidden. The settings switch `overlay.follow_game` turns this off.
"""

import time

from core.logger import get_logger

log = get_logger("game_front")

CHECK_EVERY = 0.5            # asking Windows for the window in front more than twice a second is not needed

_cache = {"at": -100.0, "away": False}
title_provider = None        # tests put a fake here; None = ask Windows


def _title():
    if title_provider is not None:
        return title_provider()
    from ui.hologram_window import foreground_title
    return foreground_title()


def away(settings, now=None):
    """True when the overlays should be hidden because Elite is not the window in front."""
    try:
        if not settings.get("overlay.follow_game", True):
            return False
        now = time.monotonic() if now is None else now
        if now - _cache["at"] < CHECK_EVERY:
            return _cache["away"]
        _cache["at"] = now
        title = _title()
        if title is None or title == "":
            _cache["away"] = False                 # cannot be read (or no window in front at all): leave the overlays alone
        else:
            from control.sender import _is_game
            _cache["away"] = not _is_game(title)
        return _cache["away"]
    except Exception:
        log.debug("Could not tell which window is in front", exc_info=True)
        return False


def reset():
    _cache["at"] = -100.0
    _cache["away"] = False
