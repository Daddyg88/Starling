"""
Listening test: checks your microphone and shows what STARLING hears.
Run it by double-clicking run_listen_test.bat.
"""

import time

from core.identity import wake_phrase
from stt.listener import HEARD, Listener
from stt.microphone import MicrophoneStream, find_microphone, list_microphones
from stt.providers import build_stt_providers, choose_stt

TEST_SECONDS = 45


def run_listen_test(app, seconds=TEST_SECONDS, out=print):
    out("LISTENING TEST")
    out("--------------")
    out("Microphones Windows can see:")
    mics = list_microphones()
    for number, name in mics or [("-", "(none found - check your microphone is plugged in)")]:
        out("  %s  %s" % (number, name))
    wanted = app.settings.get("stt.microphone", "")
    out("Using: %s" % (wanted or "the Windows default microphone"))

    providers = build_stt_providers(app.settings)
    for name, provider in providers.items():
        ok, why = provider.available()
        out("  %-15s %-30s %s" % (name, provider.label, "ready" if ok else "NOT available: " + why))
    stt = choose_stt(providers, app.settings)
    if stt is None or not mics:
        out("")
        out("Cannot test listening yet. See the lines above and docs\\TROUBLESHOOTING.md.")
        return 1

    heard = []
    app.bus.subscribe(HEARD, lambda event: heard.append(event.data))
    device = find_microphone(wanted)
    listener = Listener(app.bus, stt, app.settings, lambda: MicrophoneStream(device))
    out("")
    out("Loading the listening model (the FIRST time this downloads about 75 MB; please wait)...")
    listener.start()
    waited = 0
    while not listener.ready.is_set() and not listener.failed_reason and waited < 600:
        time.sleep(0.5)
        waited += 0.5
    if listener.failed_reason or not listener.ready.is_set():
        out("NOT ready: %s" % (listener.failed_reason or "took too long"))
        listener.stop()
        return 1
    out("Ready. For the next %d seconds, say things like:" % seconds)
    out('  "%s"' % wake_phrase(app.settings))
    out('  "%s, open the galaxy map"' % wake_phrase(app.settings))
    out("  (anything else, to see how well she understands you)")
    out("")
    shown = 0
    end = time.monotonic() + seconds
    try:
        while time.monotonic() < end:
            time.sleep(0.3)
            while shown < len(heard):
                item = heard[shown]
                shown += 1
                out('  heard: "%s"   name said: %s   request: "%s"'
                    % (item["text"], "YES" if item["wake"] else "no", item["command"]))
    except KeyboardInterrupt:
        pass
    listener.stop()
    out("")
    if heard:
        out("Listening works. She understood %d sentence(s)." % len(heard))
        return 0
    out("She heard nothing. Check the microphone is the right one, not muted, and try speaking closer.")
    out("You can pick a microphone in config\\settings.json under \"stt\" > \"microphone\".")
    return 1
