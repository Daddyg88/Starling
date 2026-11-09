"""Makes australian_sample.wav (and a few more) with MeloTTS's Australian voice, and prints how fast it is and how much memory it uses.
Run by run_try_australian_voice.bat in its own private Python folder (not Starling's). Safe to delete."""
import sys
import time


def memory_mb():
    """This program's memory use in MB (Windows), or 0 when it cannot be read."""
    try:
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
        return counters.WorkingSetSize / 1048576.0
    except Exception:
        return 0.0


started = time.time()
from melo.api import TTS

model = TTS(language="EN", device="cpu")
speakers = dict(model.hps.data.spk2id)
print("Speakers in this model:", speakers)
if "EN-AU" not in speakers:
    print("No EN-AU voice in this model")
    sys.exit(1)
print("Loaded in %.0f s. Memory in use: %.0f MB" % (time.time() - started, memory_mb()))
sentences = [
    "Good evening, Commander. Shields are up, and the jump is plotted. No worries, I have got you covered.",
    "Fuel is low.",
    "Neutron star reached. Supercharge, then head for the next system, four jumps to go.",
    "Hostile contact on the scanner. Stay sharp, Commander.",
]
for number, text in enumerate(sentences, 1):
    begin = time.time()
    name = "australian_sample.wav" if number == 1 else "australian_sample%d.wav" % number
    model.tts_to_file(text, speakers["EN-AU"], name, speed=1.0)
    print("SPEED sentence %d (%d letters): %.1f s to make. Saved %s" % (number, len(text), time.time() - begin, name))
print("Memory in use at the end: %.0f MB" % memory_mb())
