"""AUSTRALIAN VOICE WORKER. This file runs INSIDE the private MeloTTS folder (data/melo_env), never inside Starling itself.

Why: MeloTTS needs a lot of memory and its own add-ons. Keeping it in a separate program means it cannot break Starling,
and Starling can switch it off again when it has not been used for a while.

It talks in single lines of JSON on stdin/stdout:
    in : {"text": "Hello.", "speed": 1.0, "out": "C:/.../line.npy"}
    out: {"ok": true, "rate": 44100}   or   {"ok": false, "error": "why"}
The first line it prints is {"ready": true, "rate": 44100} once the voice has loaded.
Run with --fake (used by the tests) to make a plain tone without MeloTTS.
It uses only the standard library and numpy / melo, so it also works in the private folder.
"""
import json
import sys

ACCENT = "EN-AU"


def load_model(fake):
    """Returns (make_sound, rate). make_sound(text, speed) gives a float32 numpy array."""
    import numpy as np
    if fake:
        def make(text, speed):
            return np.sin(np.linspace(0, 200, 4410 + 100 * len(text))).astype(np.float32)
        return make, 44100
    from melo.api import TTS
    model = TTS(language="EN", device="cpu")
    speakers = dict(model.hps.data.spk2id)
    if ACCENT not in speakers:
        raise RuntimeError("this MeloTTS English model has no %s voice (it has %s)" % (ACCENT, ", ".join(sorted(speakers))))
    speaker = speakers[ACCENT]
    rate = int(getattr(model.hps.data, "sampling_rate", 44100) or 44100)

    def make(text, speed):
        return model.tts_to_file(text, speaker, None, speed=float(speed or 1.0))
    return make, rate


def main(argv):
    fake = "--fake" in argv
    reply = sys.stdout
    sys.stdout = sys.stderr                # MeloTTS prints progress text: it must never mix with the replies

    def send(data):
        reply.write(json.dumps(data) + "\n")
        reply.flush()

    try:
        make, rate = load_model(fake)
    except Exception as error:
        send({"ok": False, "error": "could not load: %s" % error})
        return 1
    import numpy as np
    send({"ready": True, "rate": rate})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            if request.get("quit"):
                return 0
            audio = np.asarray(make(request["text"], request.get("speed", 1.0)), dtype=np.float32).reshape(-1)
            with open(request["out"], "wb") as handle:
                np.save(handle, audio)
            send({"ok": True, "rate": rate})
        except Exception as error:
            send({"ok": False, "error": str(error)})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
