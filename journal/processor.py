"""
The EventProcessor: the middle-man between raw journal lines and the event bus.

For each line it:
  1. works out the event name,
  2. asks the matching file in events/ to update the game state and tidy the data,
  3. checks events.json (enabled? priority?),
  4. announces the result on the event bus.

SAFETY RULE: an event whose own file says it is CRITICAL is always announced
as critical, even if someone edits events.json to try to silence it.
"""

from collections import Counter

from core.event_bus import CRITICAL
from core.logger import get_logger
from journal import parser

log = get_logger("processor")


class EventProcessor:
    def __init__(self, bus, event_config, state, registry):
        self.bus = bus
        self.event_config = event_config
        self.state = state
        self.registry = registry
        self.unknown_events = 0     # lines we deliberately ignore
        self.ignored = Counter()    # which event names we ignored, and how often
        self.damaged_lines = 0
        self.skipped_by_settings = 0

    # ---- journal lines ----
    def handle_line(self, line, silent=False):
        """Process one journal line. silent=True updates state but says nothing."""
        name = parser.extract_event_name(line)
        handler = self.registry.get(name) if name else None
        if handler is None or handler.source != "journal":
            self.unknown_events += 1
            if name:
                self.ignored[name] += 1
            return
        entry = parser.parse_entry(line)
        if entry is None:
            self.damaged_lines += 1
            log.warning("Skipping a damaged journal line (%s)", name)
            return
        self.handle_entry(entry, silent)

    def handle_entry(self, entry, silent=False):
        handler = self.registry.get(entry.get("event"))
        if handler is None or handler.source != "journal":
            return
        handler.update_state(entry, self.state)
        if silent or not handler.announce:
            return
        self._announce(handler, handler.handle(entry))

    # ---- events made up from Status.json ----
    def emit(self, name, data):
        """Announce an event STARLING worked out for herself (e.g. LowFuel)."""
        handler = self.registry.get(name)
        if handler is None:
            log.error("emit() called for unknown event %s", name)
            return
        self._announce(handler, data)

    # ---- shared ----
    def _announce(self, handler, data):
        priority = handler.priority
        enabled = True
        config = self.event_config.get(handler.name)
        if config:
            enabled = config["enabled"]
            priority = config["priority"]
        if handler.priority == CRITICAL:
            priority = CRITICAL
            enabled = True
        if not enabled:
            self.skipped_by_settings += 1
            return
        data = dict(data)
        data["summary"] = handler.describe(data)
        self.bus.publish(handler.name, data, priority)

    # ---- "what did I miss?" ----
    def ignored_report(self, limit=None):
        """Lines like 'ShipTargeted: 412' for events STARLING does not know yet."""
        items = self.ignored.most_common(limit)
        return ["%s: %d" % (name, count) for name, count in items]
