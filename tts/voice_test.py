"""
Voice test: checks each part of STARLING's voice and tells you what worked.
Run it by double-clicking run_voice_test.bat.
"""

from core.identity import personalise
from tts.base_tts import VoiceSettings


def run_voice_test(app):
    print("VOICE TEST")
    print("----------")
    voice = VoiceSettings.from_settings(app.settings)

    print("Voice providers:")
    for name, provider in app.providers.items():
        ok, why = provider.available()
        print("  %-11s %-34s %s" % (name, provider.label, "ready" if ok else "NOT available: " + why))

    dialogue = app.dialogue
    keys = len(dialogue.lines)
    total = sum(len(v) for v in dialogue.lines.values())
    print("")
    print("Voice pack: %s" % (dialogue.pack_info.get("name") or "(none found)"))
    print("  %d lines under %d keys, all spoken by her cloned voice" % (total, keys))

    passed = True

    print("")
    print("Test: her cloned voice")
    kokoro = app.providers.get("kokoro")
    if kokoro is None:
        print("  The cloned voice is not set up.")
        passed = False
    else:
        print("  Loading (the FIRST time this downloads about 350 MB and tunes your recording; please wait)...")
        if not kokoro.wait_until_loaded(1800):
            print("  NOT ready: %s" % (kokoro.failed_reason or "unknown problem"))
            print("  See logs\\errors.log and docs\\TROUBLESHOOTING.md")
            passed = False
        else:
            print("  Using: %s" % kokoro.label)
            line = dialogue.pick("LoadGame", "Friendly", allow_mature=False)
            sentence = personalise(line.text, app.settings) if line else "Hello Commander."
            print('  Saying: "%s"' % sentence)
            kokoro.speak(sentence, voice)
            if kokoro.speak("This is my cloned voice. If you can hear this, speech is working.", voice):
                print("  Played OK. Did you hear her, and does it sound like your recording?")
            else:
                print("  FAILED. See logs\\errors.log")
                passed = False

    print("")
    print("All tests passed." if passed else "Something failed. Send me the text above and logs\\errors.log.")
    return 0 if passed else 1
