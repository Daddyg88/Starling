"""
Record my buttons: run it by double-clicking run_record_buttons.bat (or the Controls page in the dashboard).

  1. you type a short name for the thing you are recording (for example: request docking)
  2. a countdown, so you can get your hand on the stick and be in the game
  3. for N seconds it watches everything you press and write the timings down. It presses NOTHING.
  4. it saves a report into the "recordings" folder. Send me the .txt file and I can turn it into a macro.
"""

import re
import time

from control.binds import BindingBook
from control.recorder import InputRecorder, format_report, save_recording, suggest_macro
from core import paths


def _beep(high=True):
    try:
        import winsound
        winsound.Beep(1200 if high else 800, 150)
    except Exception:
        pass


def _flush_keyboard():
    """Throw away the keys you pressed while recording, so they do not appear in this window afterwards."""
    try:
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getwch()
    except Exception:
        pass


def countdown(seconds, out, sleep, beep):
    for left in range(int(seconds), 0, -1):
        out("   starting in %d..." % left)
        beep(False)
        sleep(1.0)


def record_and_save(app, reader, name, seconds, count=5, out=print, sleep=time.sleep, beep=_beep, flush=_flush_keyboard,
                    folder=None, book=None, clock=time.monotonic, stop=lambda: False, on_event=None):
    """Does steps 2-4. Returns (txt_path, recording). Shared by the console tool and the dashboard button."""
    from journal.locator import find_journal_folder
    journal = find_journal_folder(app.settings.get("journal.folder", "")) if app is not None else None
    book = book or BindingBook()
    book.refresh()
    recorder = InputRecorder(reader, journal_folder=journal, clock=clock, sleep=sleep)
    countdown(count, out, sleep, beep)
    out("   RECORDING for %d seconds - do your button presses now." % seconds)
    beep(True)
    recording = recorder.record(name, seconds, stop=stop, on_event=on_event)
    beep(True)
    beep(True)
    flush()
    recording.binds_file = str(book.path) if book.path else ""
    recording.binds_devices = book.joystick_names()
    txt, _raw = save_recording(recording, book, folder or paths.RECORDINGS_DIR)
    return txt, recording


def run_record_buttons(app, reader=None, out=print, ask=input, sleep=time.sleep, beep=_beep, flush=_flush_keyboard,
                       folder=None, book=None, clock=time.monotonic):
    out("RECORD MY BUTTONS")
    out("-----------------")
    out("This watches your keyboard, mouse buttons and joystick (X52) buttons and writes down what you press")
    out("and when. It presses NOTHING itself.")
    out("")
    reader = reader or app.ensure_buttons()
    if reader is None:
        out("Button reading only works on Windows.")
        return 1
    devices = reader.devices(force=True)
    if devices:
        for device in devices:
            out("   Found: %s%s" % (device.name, ("  <-- X52 HOTAS" if device.is_x52() else "  <-- HOTAS" if device.is_hotas() else "")))
    else:
        out("   No joystick found. Plug it in and run this again (keyboard and mouse still work).")
    out("")
    default = int(app.settings.get("recorder.seconds", 20) or 20)
    count = int(app.settings.get("recorder.countdown", 5) or 5)
    name = (ask("What are you recording? (e.g. request docking) ") or "").strip() or "recording"
    try:
        seconds = int((ask("How many seconds? (Enter = %d) " % default) or "").strip() or default)
    except ValueError:
        seconds = default
    seconds = max(3, min(seconds, 120))
    out("")
    out("Get into the game now. After the countdown, do the whole thing the way you would for real,")
    out("pausing where you would normally wait for the game.")
    out("")
    book = book or BindingBook()
    shown = {"n": 0}

    def live(event):
        if event["type"] == "down":
            shown["n"] += 1
            out("   %5.2fs  %s" % (event["t"], event["control"]))

    txt, recording = record_and_save(app, reader, name, seconds, count=count, out=out, sleep=sleep, beep=beep,
                                     flush=flush, folder=folder, book=book, clock=clock, on_event=live)
    out("")
    out("DONE. %d button presses were recorded." % shown["n"])
    for note in recording.notes:
        out("   Note: %s" % note)
    steps, _notes = suggest_macro(recording, book)
    if steps:
        out("   Suggested macro: %s" % ", ".join(steps))
    out("")
    out("Saved: %s" % txt)
    out("Send me that .txt file (the .json next to it is the same thing in raw form).")
    return 0
