"""
One-time voice tuning: turns your recording into STARLING's cloned voice.

What happens (only the FIRST time, because the result is saved):
  1. Read  voicepacks/default/clone/Tetko_Issued_Notice.mp3
  2. Make it the right shape: one channel (mono), 24000 Hz, at most 30 seconds.
  3. Give it to inno-kokoro, which works out the "voice fingerprint" (a tensor).
  4. Save the fingerprint as  custom_covas.pt  (in the STARLING folder).

If custom_covas.pt already exists, NOTHING is done, so start-up stays instant.
To make her re-learn the voice (for example after swapping the mp3), delete custom_covas.pt.

All the heavy libraries (torch, soundfile, inno_kokoro) are imported INSIDE the
functions that need them, so STARLING still starts fine if they are not installed.
"""

import os
import wave
from pathlib import Path

from core.logger import get_logger

log = get_logger("kokoro_setup")

SAMPLE_RATE = 24000
MAX_SECONDS = 30.0
MIN_SECONDS = 3.0
# Stay a little under the limit so we never trip it by one sample.
TRIM_SECONDS = 29.5


class VoiceSetupError(Exception):
    """Something went wrong making the cloned voice. The message is safe to show."""


# ---------------------------------------------------------------------------
# Step 2: get the recording into the right shape
# ---------------------------------------------------------------------------
def resample(audio, from_rate, to_rate):
    """Change the sample rate of a mono numpy array (band-limited, no extra packages)."""
    import numpy as np
    audio = np.asarray(audio, dtype=np.float32)
    if from_rate == to_rate or audio.size == 0:
        return audio
    new_length = max(1, int(round(audio.size * to_rate / float(from_rate))))
    spectrum = np.fft.rfft(audio)
    new_bins = new_length // 2 + 1
    resized = np.zeros(new_bins, dtype=spectrum.dtype)
    keep = min(spectrum.size, new_bins)
    resized[:keep] = spectrum[:keep]
    result = np.fft.irfft(resized, n=new_length) * (new_length / float(audio.size))
    return result.astype(np.float32)


def read_audio_file(path):
    """Read an mp3/wav/flac file. Returns (samples, sample_rate). Needs 'soundfile'."""
    try:
        import soundfile
    except ImportError as error:
        raise VoiceSetupError("The 'soundfile' add-on is missing. Re-run setup.bat.") from error
    try:
        samples, rate = soundfile.read(str(path), dtype="float32", always_2d=True)
    except Exception as error:
        raise VoiceSetupError("Could not read %s (%s)" % (Path(path).name, error)) from error
    return samples, int(rate)


def prepare_reference(samples, rate):
    """Make any recording mono, 24000 Hz and no longer than ~30 seconds."""
    import numpy as np
    samples = np.asarray(samples, dtype=np.float32)
    if samples.ndim == 2:
        samples = samples.mean(axis=1)
    samples = resample(samples, rate, SAMPLE_RATE)
    seconds = samples.size / float(SAMPLE_RATE)
    if seconds < MIN_SECONDS:
        raise VoiceSetupError(
            "The recording is only %.1f seconds long. It needs at least %d seconds of clear speech."
            % (seconds, MIN_SECONDS))
    if seconds > TRIM_SECONDS:
        samples = samples[: int(TRIM_SECONDS * SAMPLE_RATE)]
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak > 1.0:
        samples = samples / peak
    return samples


def write_wav(path, samples):
    """Save a mono float array as a 16-bit wav file (standard library only)."""
    import numpy as np
    clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm.tobytes())


# ---------------------------------------------------------------------------
# Step 3: ask inno-kokoro for the voice fingerprint
# ---------------------------------------------------------------------------
def enroll_with_inno_kokoro(wav_path):
    """
    Uses inno-kokoro:   from inno_kokoro.enroll import Tuner, enroll, read
    Returns the voice tensor.  This is the ONLY place that talks to inno-kokoro,
    so if the library ever changes, this is the only function to fix.
    """
    try:
        from inno_kokoro.enroll import Tuner, enroll, read
    except ImportError as error:
        raise VoiceSetupError(
            "inno-kokoro is not installed. Re-run setup.bat (it installs it).") from error

    log.info("Loading the inno-kokoro tuner (first time downloads about 24 MB)...")
    tuner = Tuner()
    log.info("Working out the voice fingerprint...")
    # This is the exact pattern from the inno-kokoro documentation:
    #   pack, _ = enroll(*read("my_ref.wav"), tuner)
    result = enroll(*read(str(wav_path)), tuner)
    return _extract_tensor(result)


def _extract_tensor(result):
    """inno-kokoro may hand back the tensor directly, or inside a dict/tuple."""
    if isinstance(result, dict):
        for key in ("pack", "voice", "embedding", "tensor"):
            if key in result:
                return result[key]
        if len(result) == 1:
            return next(iter(result.values()))
    if isinstance(result, (tuple, list)) and result:
        return result[0]
    return result


# ---------------------------------------------------------------------------
# Step 4: save, and the one function the app calls
# ---------------------------------------------------------------------------
def save_voice_pack(tensor, destination, saver=None):
    """Save safely: write a temporary file, then swap it in, so a crash can't leave half a file."""
    if saver is None:
        try:
            import torch
        except ImportError as error:
            raise VoiceSetupError("torch is not installed. Re-run setup.bat.") from error
        saver = torch.save
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(destination.name + ".tmp")
    try:
        saver(tensor, str(temp))
        os.replace(temp, destination)
    finally:
        if temp.exists():
            try:
                temp.unlink()
            except OSError:
                pass


def ensure_custom_voice(pack_path, reference_mp3, reader=None, enroller=None, saver=None, work_dir=None):
    """
    Make sure custom_covas.pt exists. Returns (ok, message).
    Never raises: a problem here must not stop STARLING from starting.

    reader / enroller / saver can be swapped for fakes in tests.
    """
    pack_path = Path(pack_path)
    reference_mp3 = Path(reference_mp3)
    if pack_path.is_file() and pack_path.stat().st_size > 0:
        return True, "Cloned voice already tuned (%s)." % pack_path.name
    if not reference_mp3.is_file():
        return False, ("Cannot tune her voice: the recording %s was not found. "
                       "Put it at that location and restart." % reference_mp3)

    wav_path = Path(work_dir or pack_path.parent) / "_starling_reference_24k.wav"
    try:
        log.info("Tuning the cloned voice from %s (one time only)...", reference_mp3.name)
        samples, rate = (reader or read_audio_file)(reference_mp3)
        write_wav(wav_path, prepare_reference(samples, rate))
        tensor = (enroller or enroll_with_inno_kokoro)(wav_path)
        if tensor is None:
            raise VoiceSetupError("inno-kokoro returned nothing.")
        save_voice_pack(tensor, pack_path, saver)
    except VoiceSetupError as error:
        log.error("Voice tuning failed: %s", error)
        return False, "Voice tuning failed: %s" % error
    except Exception as error:
        log.exception("Voice tuning crashed")
        return False, "Voice tuning failed: %s (details in logs\\errors.log)" % error
    finally:
        try:
            if wav_path.exists():
                wav_path.unlink()
        except OSError:
            pass
    log.info("Saved the cloned voice as %s", pack_path)
    return True, "Cloned voice tuned and saved as %s." % pack_path.name
