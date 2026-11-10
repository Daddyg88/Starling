"""Shared helpers for the journal tests."""

from core.event_bus import EventBus
from core.settings import load_event_config
from events.registry import load_registry
from journal.game_state import GameState
from journal.processor import EventProcessor


def make_processor(event_config=None):
    bus = EventBus()
    heard = []
    bus.subscribe("*", heard.append)
    config = load_event_config() if event_config is None else event_config
    if event_config is None and "InDanger" in config:
        config["InDanger"] = dict(config["InDanger"], enabled=True)      # off in the shipped file (0.92.8); the tests here check how the reader behaves when it is on
    processor = EventProcessor(bus, config, GameState(), load_registry())
    return processor, bus, heard
