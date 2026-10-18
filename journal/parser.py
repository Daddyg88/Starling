"""
Turning journal lines into Python data.

Every line in a journal file is one JSON object. Thousands of lines are
events STARLING doesn't care about (music changes, etc.), so we peek at the
event name first and only fully read the lines we actually need.
This keeps CPU use very low.
"""

import json
import re

_EVENT_NAME = re.compile(r'"event"\s*:\s*"([A-Za-z0-9_]+)"')


def extract_event_name(line):
    """Cheaply find the event name in a line, or None."""
    match = _EVENT_NAME.search(line)
    return match.group(1) if match else None


def parse_entry(line):
    """Fully read one line. Returns a dict, or None if the line is damaged."""
    try:
        entry = json.loads(line)
    except ValueError:
        return None
    return entry if isinstance(entry, dict) else None
