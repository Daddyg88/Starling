"""Finds every event file in this folder and builds the lookup table."""

import importlib
import inspect
import pkgutil

import events
from core.logger import get_logger
from events.base_event import BaseEvent

log = get_logger("registry")

_NOT_EVENTS = {"base_event", "registry"}


def load_registry():
    """Returns {"FuelScoop": <FuelScoop object>, ...}"""
    registry = {}
    for info in pkgutil.iter_modules(events.__path__):
        if info.name.startswith("_") or info.name in _NOT_EVENTS:
            continue
        try:
            module = importlib.import_module("events." + info.name)
        except Exception:
            # One broken event file must not stop STARLING from starting.
            log.exception("Could not load events/%s.py", info.name)
            continue
        found = [cls for _n, cls in inspect.getmembers(module, inspect.isclass)
                 if issubclass(cls, BaseEvent) and cls is not BaseEvent
                 and cls.__module__ == module.__name__]
        found += list(getattr(module, "EVENT_CLASSES", []))  # files that define many events
        for cls in found:
            if not cls.name:
                continue
            if cls.name in registry:
                log.warning("Event %s is defined twice", cls.name)
            registry[cls.name] = cls()
    return registry
