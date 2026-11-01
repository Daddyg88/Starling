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
import gc
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback

from core import paths
from core.logger import get_logger

log = get_logger("crash")

HEARTBEAT_FILE = "heartbeat.json"
HEARTBEAT_SECONDS = 30.0
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


def write_heartbeat(folder, started, version=""):
    """One small file, rewritten every 30 seconds: when she was last alive and how big she had grown. After a crash it shows what she
    looked like just before (a thread count or memory that keeps climbing points at a leak)."""
    data = {"saved": time.strftime("%Y-%m-%d %H:%M:%S"), "version": version, "uptime_minutes": round((time.time() - started) / 60.0, 1),
            "threads": threading.active_count(), "python_memory_blocks": sys.getallocatedblocks(), "gc_counts": list(gc.get_count())}
    tmp = folder / (HEARTBEAT_FILE + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, folder / HEARTBEAT_FILE)


def start_heartbeat(folder, version=""):
    started = time.time()

    def work():
        while True:
            try:
                write_heartbeat(folder, started, version)
            except Exception:
                pass
            time.sleep(HEARTBEAT_SECONDS)
    threading.Thread(target=work, name="heartbeat", daemon=True).start()


def read_heartbeat(folder):
    try:
        data = json.loads((folder / HEARTBEAT_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    return "Last seen alive at %s on version %s after %s minutes, %s threads, %s Python memory blocks, gc counts %s." % (
        data.get("saved"), data.get("version"), data.get("uptime_minutes"), data.get("threads"),
        data.get("python_memory_blocks"), data.get("gc_counts"))


def parse_fault_events(text):
    """Windows 'Application Error' events (from wevtutil) that mention Python or Starling -> short sentences. Never raises."""
    found = []
    for block in re.split(r"(?=^Event\[)", str(text or ""), flags=re.M):
        low = block.lower()
        if "python" not in low and "starling" not in low:
            continue
        def grab(label):
            hit = re.search(label + r":\s*([^\r\n,]+)", block, re.I)
            return hit.group(1).strip() if hit else ""
        parts = [("when", grab("Date")), ("program", grab("Faulting application name")), ("faulting module", grab("Faulting module name")),
                 ("exception code", grab("Exception code")), ("offset", grab("Fault offset"))]
        line = ", ".join("%s %s" % (k, v) for k, v in parts if v)
        found.append(line or block.strip()[:400])
    return found[:3]


def windows_fault_report(run=subprocess.run):
    """Asks Windows' own event log which file was at fault for the last crash of Python (the DLL name is the real clue). Windows only."""
    if sys.platform != "win32":
        return []
    try:
        done = run(["wevtutil", "qe", "Application", "/q:*[System[Provider[@Name='Application Error'] and TimeCreated[timediff(@SystemTime) <= 86400000]]]",
                    "/c:8", "/rd:true", "/f:text"], capture_output=True, text=True, timeout=15,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return parse_fault_events(done.stdout)
    except Exception:
        return []


def _log_windows_fault():
    for line in windows_fault_report():
        log.warning("Windows event log says: %s", line)


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
        beat = read_heartbeat(folder)
        if beat:
            log.warning(beat)
        threading.Thread(target=_log_windows_fault, name="fault-lookup", daemon=True).start()   # a few seconds; never holds up start-up
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
    start_heartbeat(folder, version)
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
