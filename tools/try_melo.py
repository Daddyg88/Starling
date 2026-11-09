"""Makes australian_sample.wav with MeloTTS's Australian voice, and prints what it found. Run by run_try_australian_voice.bat in its own
private Python folder (not Starling's). Safe to delete."""
import sys
import time

started = time.time()
from melo.api import TTS

model = TTS(language="EN", device="cpu")
speakers = dict(model.hps.data.spk2id)
print("Speakers in this model:", speakers)
if "EN-AU" not in speakers:
    print("No EN-AU voice in this model")
    sys.exit(1)
text = "Good evening, Commander. Shields are up, and the jump is plotted. No worries, I have got you covered."
made = time.time()
model.tts_to_file(text, speakers["EN-AU"], "australian_sample.wav", speed=1.0)
print("Loaded in %.0f s, made the sample in %.1f s (a sentence of about 6 seconds of speech)." % (made - started, time.time() - made))
print("Saved australian_sample.wav")
