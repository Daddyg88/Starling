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

URL = "https://huggingface.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/Qwen2.5-0.5B-Instruct-Q4_K_M.gguf"
FILE_NAME = "Qwen2.5-0.5B-Instruct-Q4_K_M.gguf"
MIN_BYTES = 200 * 1024 * 1024
MAX_BYTES = 900 * 1024 * 1024


def looks_like_model(path):
    """True if the file is a plausible GGUF model."""
    try:
        size = os.path.getsize(path)
        if not (MIN_BYTES <= size <= MAX_BYTES):
            return False
        with open(path, "rb") as handle:
            return handle.read(4) == b"GGUF"
    except OSError:
        return False


def download(url=URL, target=None, opener=urllib.request.urlopen, progress=print):
    """Returns (ok, message)."""
    if not url.lower().startswith("https://"):
        return False, "Only https downloads are allowed."
    target = target or (paths.DATA_DIR / "models" / FILE_NAME)
    target.parent.mkdir(parents=True, exist_ok=True)
    if looks_like_model(target):
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
                if done > MAX_BYTES:
                    raise ValueError("The download is bigger than expected.")
                percent = int(done * 100 / total) if total else done // (50 * 1024 * 1024)
                if percent != shown and percent % (5 if total else 1) == 0:
                    shown = percent
                    progress("  downloaded %d%s" % (percent, "%" if total else " x 50 MB"))
        if not looks_like_model(part):
            part.unlink(missing_ok=True)
            return False, "The downloaded file did not look like a model, so it was thrown away."
        os.replace(part, target)
        return True, "Done. The model is saved in %s" % target
    except Exception as exc:
        try:
            part.unlink(missing_ok=True)
        except OSError:
            pass
        return False, "The download failed: %s" % exc


if __name__ == "__main__":
    ok, message = download()
    print(message)
    sys.exit(0 if ok else 1)
