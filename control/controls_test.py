"""
Controls test: shows what STARLING can see of YOUR setup. Presses nothing in the game.
Run it by double-clicking run_controls_test.bat.

  1. finds your Elite Dangerous controls file and checks every voice command against it
  2. lists your joysticks (and says which one is the X52)
  3. for 15 seconds shows every key / mouse / joystick button you press (to pick a push-to-talk button)
  4. lets you type a sentence and tells you what she would do with it
"""

import time

from control.inputs import describe


def run_controls_test(app, reader=None, seconds=15, out=print, ask=input, sleep=time.sleep, clock=time.monotonic):
    out("CONTROLS TEST")
    out("-------------")
    runner = app.ensure_commands()
    if runner is None:
        out("Voice commands could not start. See logs\\starling.log.")
        return 1

    # 1. key bindings
    out("1) Your Elite Dangerous controls")
    working, problems = runner.binding_report()
    path = runner.book.path
    out("   File: %s" % (path if path else "NOT FOUND (%s)" % runner.book.error))
    out("   %d voice commands have a keyboard key." % working)
    for label, why in problems:
        out("   - %s" % why)
    out("")

    # 2. joysticks
    out("2) Joysticks")
    reader = reader or app.ensure_buttons()
    if reader is None:
        out("   Joystick reading only works on Windows.")
        return 0
    devices = reader.devices(force=True)
    if not devices:
        out("   None found. Plug your X52 in and run this again.")
    for device in devices:
        out("   %s  (%d buttons)%s" % (device.name, device.buttons, "   <-- X52 HOTAS" if device.is_x52() else ""))
    out("")

    # 3. live buttons
    out("3) Press keys / buttons for %d seconds. I will show each one." % seconds)
    seen = set()
    end = clock() + seconds
    while clock() < end:
        for spec in sorted(reader.snapshot() - seen):
            out("   %-22s %s" % (spec, describe(spec, devices)))
            seen.add(spec)
        sleep(0.05)
    out("   (Copy one into  ptt.button  in config\\settings.json, or use the Learn button on the Controls page.)")
    out("")

    # 4. try sentences
    out("4) Type something you would say (empty line to finish). Nothing is pressed.")
    while True:
        try:
            text = ask("   You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            break
        for line in runner.explain(text):
            out("   -> " + line)
    return 0
