"""Her voice on your graphics card, without a command window.

Her voice (Kokoro) runs on "torch". The torch that comes with Starling runs on the processor (a sentence takes about 3 seconds to
start). The NVIDIA build of torch runs on the graphics card (about ten times faster) but it is a 2.5 GB download.

This installs that build into its OWN folder (data/torch_gpu) with `pip install --target`, so the normal torch is never touched, and
main.py puts that folder first in Python's search path at start-up (activate(), below) so the graphics-card torch is the one that loads.
Because it only adds a folder, undoing it is deleting the folder (remove()), and it works the same for Starling.exe, the installed
copy and a source install (the exe is only a launcher: the program itself always runs in a private Python with pip).

Safety: each version is tried in a separate Python first (it must import and say the graphics card is usable) and thrown away if not;
if Starling starts twice with it and never gets her voice running, it is put aside by itself."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from core import paths
from core.logger import get_logger

log = get_logger("gputorch")

TAGS = ("cu126", "cu124", "cu128", "cu118")       # NVIDIA CUDA builds, newest first; the first that works is kept
INDEX = "https://download.pytorch.org/whl/%s"
MIN_FREE_GB = 7                                   # the download is about 2.5 GB, pip needs room to unpack and test
MAX_FAILED_STARTS = 3
NO_VOICE_FLAGS = ("--check", "--silent", "--demo", "--listen-test", "--controls-test", "--record-buttons", "--debug")
CREATE_NO_WINDOW = 0x08000000


def folder():
    return paths.DATA_DIR / "torch_gpu"


def _marker(base=None):
    return Path(base or folder()) / "starling_gpu.json"


def installed(base=None):
    try:
        return _marker(base).is_file() and (Path(base or folder()) / "torch").is_dir()
    except OSError:
        return False


def _read(base=None):
    try:
        return json.loads(_marker(base).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(info, base=None):
    try:
        _marker(base).write_text(json.dumps(info), encoding="utf-8")
    except OSError:
        pass


def _restore_aside(base):
    """0.96.154: an old bug used up the tries after a harmless crash and put a good 2.5 GB library aside. A NEWER Starling
    than the one that put it aside gives it back (no new download). Returns a sentence, or ''."""
    aside = base.with_name(base.name + ".broken")
    if installed(base) or not installed(aside):
        return ""
    try:
        from core.version import __version__
    except Exception:
        __version__ = ""
    info = _read(aside)
    if info.get("version") == __version__:                      # this very version put it aside: do not loop
        return ""
    try:
        os.replace(str(aside), str(base))
    except OSError:
        return ""
    info["version"] = __version__
    info["starts_without_voice"] = 0
    _write(info, base)
    return "The graphics-card voice library that an older Starling put aside was put back. "


def activate(base=None, path=None):
    """Called by main.py BEFORE anything imports torch. Returns a sentence for the log, or '' when there is nothing to do."""
    base = Path(base or folder())
    path = sys.path if path is None else path
    restored = _restore_aside(base)
    if not installed(base):
        return ""
    info = _read(base)
    failed = int(info.get("starts_without_voice", 0) or 0)
    try:
        from core.version import __version__
    except Exception:
        __version__ = ""
    if info.get("version") != __version__:                      # a new Starling gets a fresh set of tries (an old bug could use them all up)
        failed = 0
        info["version"] = __version__
        info["starts_without_voice"] = 0
        _write(info, base)
    if failed >= MAX_FAILED_STARTS:
        aside = base.with_name(base.name + ".broken")
        shutil.rmtree(aside, ignore_errors=True)
        try:
            os.replace(str(base), str(aside))
        except OSError:
            shutil.rmtree(base, ignore_errors=True)
        return ("The graphics-card voice library was put aside: Starling started %d times with it and her voice never came up. "
                "She uses the processor voice again. Press 'Run her voice on the graphics card' to try again." % failed)
    if not any(flag in sys.argv for flag in NO_VOICE_FLAGS):    # a start that never loads her voice must not count as a failed one
        info["starts_without_voice"] = failed + 1
        _write(info, base)                                     # the voice engine clears this once it is running (voice_ok)
    if str(base) not in path:
        path.insert(0, str(base))
    return restored + "Using the graphics-card torch from %s" % base


def voice_ok(base=None):
    """The voice engine started: the graphics-card library is fine, forget the failed-start count."""
    base = Path(base or folder())
    if installed(base):
        info = _read(base)
        if info.get("starts_without_voice"):
            info["starts_without_voice"] = 0
            _write(info, base)


def remove(base=None):
    shutil.rmtree(base or folder(), ignore_errors=True)
    shutil.rmtree(Path(base or folder()).with_name("torch_gpu.broken"), ignore_errors=True)


def _run(command, **kwargs):
    flags = CREATE_NO_WINDOW if sys.platform == "win32" else 0
    return subprocess.run(command, capture_output=True, text=True, creationflags=flags, **kwargs)


def _probe_script(base):
    return ("import sys; sys.path.insert(0, %r); import torch; print('torch', torch.__version__, torch.cuda.is_available()); "
            "sys.exit(0 if torch.cuda.is_available() and '+cu' in torch.__version__ else 1)" % str(base))


def install(progress=print, run=None, free_bytes=None, python=None, base=None, platform_name=None, tags=TAGS):
    """Returns (ok, sentence). 'run' (command -> object with returncode, stdout, stderr), 'free_bytes' and 'platform_name' are for tests."""
    platform_name = platform_name or sys.platform
    if platform_name != "win32":
        return False, "This only works on Windows with an NVIDIA graphics card."
    run = run or _run
    python = python or sys.executable
    base = Path(base or folder())
    if installed(base):
        return True, "The graphics-card voice library is already installed. Restart Starling if her voice is not on the graphics card yet."
    try:
        if run(["nvidia-smi"]).returncode != 0:
            raise OSError("nvidia-smi failed")
    except Exception:
        return False, ("I could not find an NVIDIA graphics card driver (nvidia-smi did not run). This only helps PCs with an NVIDIA card. "
                       "If you have one, update its driver from nvidia.com and try again. Nothing was changed.")
    from tts import voice_space
    free = (free_bytes or voice_space.free_bytes)()
    if free is not None and free < MIN_FREE_GB * 1073741824:
        return False, ("There is not enough free disk space: this needs about %d GB and the drive has %s. Free some space and try again. "
                       "Nothing was changed." % (MIN_FREE_GB, voice_space.gb(free)))
    last = ""
    for tag in tags:
        shutil.rmtree(base, ignore_errors=True)
        base.mkdir(parents=True, exist_ok=True)
        progress("Downloading the graphics-card version of her voice library (%s, about 2.5 GB). This takes a few minutes; you can keep using Starling..." % tag)
        done = run([python, "-m", "pip", "install", "--no-deps", "--upgrade", "--target", str(base), "torch", "--index-url", INDEX % tag])
        if done.returncode != 0:
            last = "the %s version could not be downloaded" % tag
            log.warning("Graphics-card torch %s: pip failed: %s", tag, (getattr(done, "stderr", "") or "")[-300:])
            continue
        progress("Checking that it works on this PC...")
        probe = run([python, "-I", "-c", _probe_script(base)])
        if probe.returncode != 0:
            last = "the %s version did not find a usable graphics card" % tag
            log.warning("Graphics-card torch %s: check failed: %s %s", tag, (getattr(probe, "stdout", "") or "")[-200:], (getattr(probe, "stderr", "") or "")[-300:])
            continue
        _write({"tag": tag, "starts_without_voice": 0}, base)
        log.info("Graphics-card torch %s installed in %s", tag, base)
        return True, "Done. Restart Starling: her voice will run on your graphics card (the log will say 'cuda')."
    shutil.rmtree(base, ignore_errors=True)
    return False, "None of the graphics-card versions worked on this PC (%s). Her voice still works as before, on the processor. Nothing else was changed." % (last or "see the log")
