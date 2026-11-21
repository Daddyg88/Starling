"""
Downloads the small chat model once (about 400 MB) into data/models. Used by run_install_chat_model.bat.

Safety: HTTPS only, from the address below, written to a temporary file first, and only kept if the size is sensible and
the file starts with the GGUF marker (so a web page or an error is never mistaken for a model).
Run:  python -m core.model_download
"""
import os
import sys
import urllib.request

from core import paths
from core.secure_open import is_certificate_problem, open_url

URL = "https://huggingface.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf"
FILE_NAME = "Qwen2.5-0.5B-Instruct-Q4_K_M.gguf"
MIN_BYTES = 200 * 1024 * 1024
MAX_BYTES = 900 * 1024 * 1024

# The chat models she can use (0.96.128). All Qwen2.5 Instruct, Apache 2.0 licence, from the same Hugging Face maker. "small" is the one every install gets.
# size name: (file name, address, smallest and biggest sensible size in bytes, how it is described on the screen)
MB = 1024 * 1024
MODELS = {
    "small": (FILE_NAME, URL, MIN_BYTES, MAX_BYTES, "Small (about 400 MB, fast, simple replies)"),
    "better": ("Qwen2.5-3B-Instruct-Q4_K_M.gguf",
               "https://huggingface.co/bartowski/Qwen2.5-3B-Instruct-GGUF/resolve/main/Qwen2.5-3B-Instruct-Q4_K_M.gguf",
               1500 * MB, 2800 * MB, "Better (about 2 GB, clearer replies, needs a 4+ core PC)"),
    "high": ("Qwen2.5-7B-Instruct-Q4_K_M.gguf",
             "https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf",
             3800 * MB, 6000 * MB, "High (about 4.7 GB, the smartest, needs a strong PC with 8+ cores and 16 GB RAM or more)"),
}


def spec(size):
    """(file name, address, min bytes, max bytes, description) for 'small', 'better' or 'high' (anything else = small)."""
    return MODELS.get(str(size or "small").lower(), MODELS["small"])


def looks_like_model(path, min_bytes=MIN_BYTES, max_bytes=MAX_BYTES):
    """True if the file is a plausible GGUF model."""
    try:
        size = os.path.getsize(path)
        if not (min_bytes <= size <= max_bytes):
            return False
        with open(path, "rb") as handle:
            return handle.read(4) == b"GGUF"
    except OSError:
        return False


def download(url=URL, target=None, opener=open_url, progress=print, min_bytes=MIN_BYTES, max_bytes=MAX_BYTES):
    """Returns (ok, message)."""
    if not url.lower().startswith("https://"):
        return False, "Only https downloads are allowed."
    target = target or (paths.DATA_DIR / "models" / FILE_NAME)
    target.parent.mkdir(parents=True, exist_ok=True)
    if looks_like_model(target, min_bytes, max_bytes):
        return True, "The model is already there."
    part = target.with_name(target.name + ".part")
    try:
        with opener(url, timeout=60) as response, open(part, "wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            done, shown = 0, -1
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if done > max_bytes:
                    raise ValueError("The download is bigger than expected.")
                percent = int(done * 100 / total) if total else done // (50 * 1024 * 1024)
                if percent != shown and percent % (5 if total else 1) == 0:
                    shown = percent
                    progress("  downloaded %d%s" % (percent, "%" if total else " x 50 MB"))
        if not looks_like_model(part, min_bytes, max_bytes):
            part.unlink(missing_ok=True)
            return False, "The downloaded file did not look like a model, so it was thrown away."
        os.replace(part, target)
        return True, "Done. The model is saved in %s" % target
    except Exception as exc:
        try:
            part.unlink(missing_ok=True)
        except OSError:
            pass
        if is_certificate_problem(exc) or is_certificate_problem(getattr(exc, "reason", None)):
            return False, ("Your PC does not trust Hugging Face's security certificate, so the model download was refused. Antivirus "
                           "'web shield' or 'HTTPS scanning' is the usual cause: pause it for a few minutes and try again.")
        return False, "The download failed: %s" % exc


def download_size(size="small", opener=open_url, progress=print):
    """Downloads the chat model of that size ('small', 'better' or 'high') into data/models. Returns (ok, message)."""
    file_name, url, low, high, _text = spec(size)
    return download(url, paths.DATA_DIR / "models" / file_name, opener, progress, low, high)


if __name__ == "__main__":
    ok, message = download_size(sys.argv[1] if len(sys.argv) > 1 else "small")
    print(message)
    sys.exit(0 if ok else 1)
