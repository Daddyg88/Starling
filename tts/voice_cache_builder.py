"""
Pre-makes the sound for every line she can say, so nothing ever has to be generated
while you are flying. Run it by double-clicking run_build_voice_cache.bat.
It is safe to run again: lines that are already done are skipped instantly.
"""

from core.identity import personalise
from tts.kokoro_tts import speed_from_rate


def collect_texts(dialogue, allow_mature=False, settings=None):
    """Every fixed line (lines with {placeholders}, like the fuel percentage, are made on the spot)."""
    texts = []
    seen = set()
    for lines in dialogue.lines.values():
        for line in lines:
            if line.mature and not allow_mature:
                continue
            for text in (part.strip() for part in personalise(line.text, settings).split("||")):
                if not text or "{" in text or text in seen:
                    continue
                seen.add(text)
                texts.append(text)
    return texts


def build_voice_cache(app, out=print):
    kokoro = app.providers.get("kokoro")
    if kokoro is None or app.dialogue is None:
        out("The cloned voice is not set up.")
        return 1
    out("Loading the voice (the first time this downloads about 350 MB and tunes your recording)...")
    if not kokoro.wait_until_loaded(1800):
        out("NOT ready: %s" % (kokoro.failed_reason or "unknown problem"))
        return 1
    speed = speed_from_rate(app.settings.get("tts.rate", 0))
    texts = collect_texts(app.dialogue, bool(app.settings.get("speech.allow_mature", False)), app.settings)
    out("Making %d lines. Please wait..." % len(texts))
    failed = 0
    for number, text in enumerate(texts, 1):
        if not kokoro.render(text, speed):
            failed += 1
        if number % 25 == 0 or number == len(texts):
            out("  %d of %d" % (number, len(texts)))
    out("Done. %d lines ready%s." % (len(texts) - failed, (", %d failed (see logs\\errors.log)" % failed) if failed else ""))
    return 1 if failed else 0
