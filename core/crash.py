"""
Finding out why she stopped.

Until now a sudden stop left nothing in the log. This does three small things, all of them cheap:

  1. Python errors nobody caught (in the main program or in any background thread) are written to logs/starling.log, logs/errors.log
     and logs/crash.log with the full "traceback" (the list of what was running).
  2. A real crash inside a library (the voice, the listening model, the window) writes what every thread was doing to logs/crash.log.
  3. A small marker file, logs/running.flag, is made at start and removed on a clean stop. If it is still there next time, she says
     so in the log ("the last run did not stop cleanly, it started at 19:43") and copies the end of crash.log into the log, so the
     log you send already shows the reason.

Nothing here runs while she is working; it only wakes up when something goes wrong.
"""

import faulthandler
import os
import sys
import threading
import time
import traceback

from core import paths
from core.logger import get_logger

log = get_logger("crash")

CRASH_FILE = "crash.log"
FLAG_FILE = "running.flag"
LAST_CRASH_FILE = "crash_last.log"
SHOW_CHARS = 3000                    # how much of an old crash report is copied into the main log

_handle = None                       # faulthandler needs its file kept open for as long as the program runs
_state = {"folder": None}


def _folder(logs_dir=None):
    return logs_dir or paths.LOGS_DIR


def _read_tail(path, chars=SHOW_CHARS):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-chars:].strip()


def report_previous(logs_dir=None):
    """Look at what the last run left behind. Returns a short sentence (or '') and writes the details into the log."""
    folder = _folder(logs_dir)
    flag, crash = folder / FLAG_FILE, folder / CRASH_FILE
    said = ""
    unclean = flag.exists()
    started = ""
    if unclean:
        try:
            started = flag.read_text(encoding="utf-8", errors="replace").strip().splitlines()[0]
        except (OSError, IndexError):
            started = ""
    details = _read_tail(crash) if crash.exists() else ""
    if unclean:
        said = "The last run did not stop cleanly%s." % (" (it started at %s)" % started if started else "")
        log.warning("%s It may have crashed, been closed from the Task Manager, or lost power.", said)
    if details:
        log.warning("The last crash report (logs\\%s):\n%s", CRASH_FILE, details)
        try:
            os.replace(crash, folder / LAST_CRASH_FILE)          # keep it, but do not report it twice
        except OSError:
            pass
        said = said or "The last run crashed."
    return said


def install(logs_dir=None, version=""):
    """Call once, as early as possible in main(). Safe to call twice."""
    global _handle
    folder = _folder(logs_dir)
    _state["folder"] = folder
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    report_previous(folder)
    try:
        flag = folder / FLAG_FILE
        flag.write_text("%s\nversion %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), version or "?"), encoding="utf-8")
    except OSError:
        pass
    try:
        if _handle is None:
            _handle = open(folder / CRASH_FILE, "a", encoding="utf-8")
            faulthandler.enable(file=_handle, all_threads=True)
    except (OSError, RuntimeError, ValueError):
        log.warning("Could not set up the crash report file", exc_info=True)
    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook
    return True


def mark_clean_exit(logs_dir=None):
    """Call when she stops on purpose: removes the marker so the next start knows all was well."""
    try:
        (_folder(logs_dir) / FLAG_FILE).unlink()
    except OSError:
        pass


def _write_crash(title, exc_type, value, tb):
    text = "".join(traceback.format_exception(exc_type, value, tb))
    log.critical("%s\n%s", title, text)
    folder = _state.get("folder")
    if folder is not None and _handle is not None:
        try:
            _handle.write("\n%s  %s\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), title, text))
            _handle.flush()
        except (OSError, ValueError):
            pass


def _excepthook(exc_type, value, tb):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, value, tb)
        return
    _write_crash("An error nobody caught stopped the program", exc_type, value, tb)


def _thread_excepthook(args):
    if args.exc_type is SystemExit:
        return
    name = getattr(args.thread, "name", "a background thread")
    _write_crash("A background thread (%s) stopped with an error" % name, args.exc_type, args.exc_value, args.exc_traceback)
