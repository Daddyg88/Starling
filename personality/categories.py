"""
Which dashboard tab an event belongs to, and whether that tab's "She comments on ..." switch is on.
The lists are in config/categories.json. Safety warnings (critical events) are never silenced here.
"""
import json

from core import paths
from core.logger import get_logger

log = get_logger("categories")

TABS = ("combat", "exploration", "exobiology", "mining", "trading", "antixeno")
_cache = None


def _load(path=None):
    path = path or (paths.CONFIG_DIR / "categories.json")
    mapping = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        for tab in TABS:
            for name in raw.get(tab, []):
                mapping[str(name)] = tab
    except FileNotFoundError:
        pass
    except (OSError, ValueError, AttributeError):
        log.exception("Could not read %s", path)
    return mapping


def mapping():
    global _cache
    if _cache is None:
        _cache = _load()
    return _cache


def reload(path=None):
    global _cache
    _cache = _load(path)


def category_of(name, data=None):
    """The tab for an event, or None when it does not belong to one."""
    data = data or {}
    if data.get("Announce") == "thargoid":
        return "antixeno"
    if name in ("SAASignalsFound", "FSSBodySignals") and data.get("Biological"):
        return "exobiology"
    return mapping().get(name)


def allowed(event, settings):
    """False when the event's tab has "She comments on ..." switched off. Critical events are always allowed."""
    if getattr(event, "priority", "") == "critical":
        return True
    if event.name == "HighGradeHint":
        try:
            if not settings.get("exploration.hge_hint", True):
                return False
        except Exception:
            pass
    tab = category_of(event.name, event.data or {})
    if tab is None:
        return True
    try:
        return bool(settings.get("talk." + tab, True))
    except Exception:
        return True
