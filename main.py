"""
STARLING - AI ship companion for Elite Dangerous.

This is the "start button" for the whole program.

    python main.py            watch Elite Dangerous live (normal use)
    python main.py --demo     replay a pretend session (no game needed)
    python main.py --demo --fast   same, with no pauses
    python main.py --check    start up, report, and stop
    python main.py --voice-test   test her voice, then stop
    python main.py --build-voice-cache   pre-make every line in her voice (so they play instantly)
    python main.py --listen   same as normal, and she listens for your voice
    python main.py --listen-test   test your microphone and listening, then stop
    python main.py --controls-test   check your Elite keys, joystick and what she'd do with a sentence
    python main.py --record-buttons   record the buttons you press (for building macros)
    python main.py --silent   same as normal but with the voice switched off
    python main.py --debug    show everything the game writes (for finding problems)
"""

import argparse
import logging
import os
import sys
import time
import warnings

# Keep the console tidy: hide harmless warnings from the voice downloader.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
warnings.filterwarnings("ignore", message=".*symlinks.*")
warnings.filterwarnings("ignore", message=".*unauthenticated.*")
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

# STARLING needs a reasonably modern Python. Check before anything else.
if sys.version_info < (3, 10):
    print("STARLING needs Python 3.10 or newer (3.12 is recommended).")
    print("You are using Python %d.%d." % sys.version_info[:2])
    sys.exit(1)

from core.app import App
from core.identity import wake_phrase


def _make_console_safe():
    """Stop odd characters in system names from crashing the window."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main():
    _make_console_safe()
    options = argparse.ArgumentParser(description="STARLING ship companion")
    options.add_argument("--demo", action="store_true", help="replay a pretend play session")
    options.add_argument("--fast", action="store_true", help="demo without pauses")
    options.add_argument("--check", action="store_true", help="start up, report, stop")
    options.add_argument("--voice-test", action="store_true", help="test her voice")
    options.add_argument("--build-voice-cache", action="store_true", help="pre-make every voice line")
    options.add_argument("--listen", action="store_true", help="listen for your voice")
    options.add_argument("--listen-test", action="store_true", help="test the microphone")
    options.add_argument("--dashboard", action="store_true", help="open the dashboard window")
    options.add_argument("--controls-test", action="store_true", help="check keys, joystick, sentences")
    options.add_argument("--record-buttons", action="store_true", help="record button presses and timing")
    options.add_argument("--silent", action="store_true", help="no speech")
    options.add_argument("--debug", action="store_true", help="show everything the game writes")
    args = options.parse_args()

    app = App()
    try:
        # Demo mode never saves its pretend events into your real history.
        app.start(record_events=not args.demo, show_events=not (args.check or args.voice_test or args.build_voice_cache or args.listen_test or args.controls_test or args.record_buttons or args.dashboard))
        for line in app.status_report():
            print(line)

        if args.debug:
            from core import paths
            from journal.debug_watch import run_debug
            from journal.locator import find_journal_folder
            folder = find_journal_folder(app.settings.get("journal.folder", ""))
            if folder is None:
                print("I could not find the Elite Dangerous journal folder.")
                return 1
            target = paths.LOGS_DIR / "debug_session.txt"
            print("DEBUG MODE. Everything is saved to %s" % target)
            print("")
            run_debug(folder, target)
            return 0

        speaking = False
        if not (args.silent or args.check or args.fast or args.listen_test or args.controls_test or args.record_buttons):
            speaking = app.start_speech()

        if args.controls_test:
            from control.controls_test import run_controls_test
            return run_controls_test(app)

        if args.record_buttons:
            from control.record_buttons import run_record_buttons
            return run_record_buttons(app)

        if args.listen_test:
            from stt.listen_test import run_listen_test
            return run_listen_test(app)

        if args.build_voice_cache:
            if not speaking:
                app.settings.set("speech.enabled", True)
                speaking = app.start_speech()
            from tts.voice_cache_builder import build_voice_cache
            return build_voice_cache(app)

        if args.voice_test:
            if not speaking:
                app.settings.set("speech.enabled", True)
                speaking = app.start_speech()
            from tts.voice_test import run_voice_test
            return run_voice_test(app)

        if args.check:
            print("Startup check complete. Everything is working.")
            print("")
            return 0

        if args.demo:
            from journal.replay import run_demo
            print("DEMO MODE: replaying a pretend play session.")
            print("")
            delay = 0.0 if args.fast else (2.5 if speaking else 0.6)
            run_demo(app.processor, delay=delay)
            if speaking:
                app.speech.wait_until_idle(20)
            print("")
            print("Demo finished.")
            return 0

        if (args.listen or app.settings.get("stt.enabled", False)) and speaking:
            ok, why = app.start_listening()
            print("Listening: ON (say \"%s\" then your request)" % wake_phrase(app.settings)
                  if ok else "Listening: OFF - %s" % why)

        if args.dashboard:
            if speaking and app.listener is None and app.settings.get("stt.enabled", False):
                app.start_listening()
            app.start_monitor()
            app.ensure_updates().check_in_background(app.log)
            from ui.dashboard import run_dashboard
            return run_dashboard(app)

        folder = app.start_monitor()
        if folder is None:
            print("I could not find the Elite Dangerous journal folder.")
            print("It is normally:")
            print(r"  C:\Users\<you>\Saved Games\Frontier Developments\Elite Dangerous")
            print("If yours is somewhere else, put its path in config\\settings.json")
            print('under "journal" > "folder". See docs\\PHASE2_GUIDE.md.')
            return 1
        print("Watching: %s" % folder)
        print("Start Elite Dangerous (or just play). Press Ctrl+C to stop.")
        print("")
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("")
        print("Stopping STARLING...")
        top = app.processor.ignored_report(10) if app.processor else []
        if top:
            print("")
            print("Journal events I don't know yet (most common first):")
            for line in top:
                print("   " + line)
            print("The full list is saved in logs\\ignored_events.txt")
        return 0
    except Exception as error:  # show a friendly message instead of a scary crash
        print("")
        print("STARLING could not start: %s" % error)
        print("Details were saved in the logs folder (errors.log).")
        return 1
    finally:
        app.stop()


if __name__ == "__main__":
    sys.exit(main())
