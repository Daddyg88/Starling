"""One zip with everything needed to work out why something is not working, with secrets taken out.

Contents: the newest log files, settings (keys, tokens and passwords replaced by '***'), version and computer info, and the
sizes of her data files. Nothing from the game journals or her memories is included."""
import json
import platform
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

SECRET_WORDS = ("key", "token", "secret", "password", "passwd", "auth")
MAX_LOGS = 4
MAX_LOG_BYTES = 6 * 1024 * 1024          # per log file: the newest part is kept if it is bigger


def redact(value, name=""):
    """A copy of settings with anything that looks like a secret replaced by '***' (empty ones are left empty)."""
    if isinstance(value, dict):
        return {key: redact(item, str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item, name) for item in value]
    if isinstance(value, str) and value and any(word in name.lower() for word in SECRET_WORDS):
        return "***"
    return value


def system_info(version):
    return {"version": version, "python": platform.python_version(), "windows": platform.platform(), "frozen": bool(getattr(sys, "frozen", False)),
            "made": datetime.now().isoformat(timespec="seconds")}


def data_sizes(data_dir):
    sizes = {}
    try:
        for item in sorted(Path(data_dir).iterdir()):
            if item.is_file():
                sizes[item.name] = item.stat().st_size
            elif item.is_dir():
                sizes[item.name + "/"] = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())
    except OSError:
        pass
    return sizes


def _tail(path, limit):
    size = path.stat().st_size
    with open(path, "rb") as handle:
        if size > limit:
            handle.seek(size - limit)
            handle.readline()                      # start on a whole line
        return handle.read()


def make_bundle(settings_path, logs_dir, data_dir, version, target_dir):
    """Writes starling-diagnostics-<date>.zip into target_dir and returns its path."""
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    out = target / ("starling-diagnostics-%s.zip" % datetime.now().strftime("%Y%m%d-%H%M%S"))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as bundle:
        try:
            settings = json.loads(Path(settings_path).read_text(encoding="utf-8"))
            bundle.writestr("settings-without-secrets.json", json.dumps(redact(settings), indent=2))
        except (OSError, ValueError):
            bundle.writestr("settings-without-secrets.json", "{}")
        bundle.writestr("about.json", json.dumps({**system_info(version), "data_files": data_sizes(data_dir)}, indent=2))
        try:
            logs = sorted(Path(logs_dir).glob("starling.log*"), key=lambda p: p.stat().st_mtime, reverse=True)[:MAX_LOGS]
        except OSError:
            logs = []
        for log in logs:
            try:
                bundle.writestr("logs/" + log.name, _tail(log, MAX_LOG_BYTES))
            except OSError:
                continue
        try:                                                  # the little black-and-white maps of failed panel looks (no game pictures)
            for png in sorted((Path(data_dir) / "panel_debug").glob("*.png"))[-24:]:
                bundle.write(png, "panel_debug/" + png.name)
        except OSError:
            pass
    return out


def looks_like_secret(text):
    """Used by tests: a quick check that a bundle's text still holds no key-like value."""
    return bool(re.search(r"AIza[0-9A-Za-z_-]{20,}|ghp_[0-9A-Za-z]{20,}|oauth:[0-9a-z]{20,}", text))
