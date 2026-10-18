"""
Debug mode: shows EVERYTHING the game writes, so problems can be tracked down.

  * every change in Status.json (which switches turned on or off, the screen...)
  * the name of every journal event, even the ones STARLING ignores

Everything is also saved to logs\\debug_session.txt so it can be sent for help.
That file contains your commander name and where you were in the game.
"""

import json
import time
from pathlib import Path

from events.status_flags import FLAGS2_NAMES, FLAGS_NAMES
from journal.parser import extract_event_name
from journal.watcher import JournalWatcher

_STATUS_KEYS = ("GuiFocus", "FireGroup", "LegalState", "SelectedWeapon", "BodyName")


def _names(value, table):
    return {table.get(bit, "bit%d" % bit) for bit in range(32) if value & (1 << bit)}


class _Printer:
    def __init__(self, log_path):
        self.log_file = open(log_path, "w", encoding="utf-8")

    def say(self, text):
        stamp = time.strftime("%H:%M:%S")
        line = "[%s] %s" % (stamp, text)
        print(line, flush=True)
        self.log_file.write(line + "\n")
        self.log_file.flush()

    def close(self):
        self.log_file.close()


class _JournalTap:
    """Looks like the EventProcessor, but just prints."""

    def __init__(self, printer):
        self.printer = printer

    def handle_line(self, line, silent=False):
        if silent:
            return
        name = extract_event_name(line) or "?"
        short = line if len(line) <= 260 else line[:260] + "..."
        self.printer.say("JOURNAL  %-22s %s" % (name, short))


def run_debug(folder, log_path, stop_check=lambda: False, poll=0.25):
    printer = _Printer(log_path)
    watcher = JournalWatcher(folder, _JournalTap(printer))
    status_path = Path(folder) / "Status.json"
    last = {"Flags": 0, "Flags2": 0}
    signature = None
    printer.say("Debug started. Watching %s" % folder)
    printer.say("Do the thing that goes wrong (enter the Nomad, step outside...), then press Ctrl+C.")
    try:
        while not stop_check():
            watcher.poll_once()
            try:
                info = status_path.stat()
                sig = (info.st_mtime_ns, info.st_size)
                if sig != signature:
                    signature = sig
                    with open(status_path, "r", encoding="utf-8") as handle:
                        status = json.load(handle)
                    _show_status(printer, last, status)
            except (OSError, ValueError):
                signature = None
            time.sleep(poll)
    finally:
        printer.close()


def _show_status(printer, last, status):
    flags = int(status.get("Flags") or 0)
    flags2 = int(status.get("Flags2") or 0)
    changes = []
    on = _names(flags, FLAGS_NAMES) - _names(last["Flags"], FLAGS_NAMES)
    off = _names(last["Flags"], FLAGS_NAMES) - _names(flags, FLAGS_NAMES)
    on2 = _names(flags2, FLAGS2_NAMES) - _names(last["Flags2"], FLAGS2_NAMES)
    off2 = _names(last["Flags2"], FLAGS2_NAMES) - _names(flags2, FLAGS2_NAMES)
    for label, names in (("ON ", on), ("OFF", off), ("ON  (Flags2)", on2), ("OFF (Flags2)", off2)):
        if names:
            changes.append("%s: %s" % (label, ", ".join(sorted(names))))
    extras = ["%s=%s" % (k, status[k]) for k in _STATUS_KEYS if k in status]
    main = (status.get("Fuel") or {}).get("FuelMain")
    if isinstance(main, (int, float)):
        extras.append("FuelMain=%.2f" % main)
    if changes or last.get("extras") != extras:
        printer.say("STATUS   Flags=%d Flags2=%d  %s  %s" % (flags, flags2, " | ".join(changes), " ".join(extras)))
    last["Flags"], last["Flags2"], last["extras"] = flags, flags2, extras
