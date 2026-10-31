"""
THE UPDATER - gets new versions of Starling from your GitHub releases, safely.

Uses only Python's built-in libraries, because the little launcher program (Starling.exe) uses it too.

How an update works (and why it can't leave you with a half-installed Starling):
  1. CHECK    Ask GitHub for the newest release of your repository and compare its version number with ours.
  2. DOWNLOAD The release's  Starling-app.zip  and its  Starling-app.zip.sha256  fingerprint. If the fingerprint doesn't match
              the download (broken or tampered), it is thrown away.
  3. STAGE    The zip is unpacked into a separate "updates/pending" folder. Nothing live is touched yet.
  4. APPLY    Next time Starling starts (the launcher does this, before the program is running so no file is in use):
                 - your data, settings, recordings and logs are copied into the new copy,
                 - the live folder is renamed to "app.previous" and the new one renamed into place.
              Two quick renames: it is either the old version or the new one, never a mixture.
              If anything goes wrong the old folder is renamed straight back.
"""
import hashlib
import json
import os
import re
import shutil
import ssl
import urllib.request
import zipfile
from pathlib import Path

ASSET_ZIP = "Starling-app.zip"
ASSET_SHA = "Starling-app.zip.sha256"
# Things that belong to YOU, not to the program. They are carried over into every new version.
KEEP = ["data", "recordings", "logs", "config/settings.json", "plugins", "custom_covas.pt"]
USER_AGENT = "Starling-updater"
MAX_ZIP_BYTES = 400 * 1024 * 1024


class UpdateError(Exception):
    pass


def parse_version(text):
    """'v0.11.0' -> (0, 11, 0).  Anything after the numbers is ignored.  Bad text -> ()."""
    found = re.match(r"\s*v?(\d+(?:\.\d+)*)", str(text or ""))
    return tuple(int(part) for part in found.group(1).split(".")) if found else ()


def is_newer(latest, current):
    a, b = parse_version(latest), parse_version(current)
    if not a or not b:
        return False
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


from core.secure_open import certifi_context as _certifi_context, is_certificate_problem as _is_certificate_problem   # shared with the AI chat download


def _open(url, token="", opener=None, timeout=30):
    """Opens the address. Some Windows PCs do not yet trust the certificate GitHub uses ("unable to get issuer certificate"), so on that
    one error it tries again with the certifi certificate list. The certificate is still checked; it is never switched off."""
    opener = opener or urllib.request.urlopen
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    try:
        return opener(request, timeout=timeout)
    except Exception as error:
        context = _certifi_context() if _is_certificate_problem(error) else None
        if context is None:
            raise
        return opener(request, timeout=timeout, context=context)


def _valid_repo(repo):
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", str(repo or "").strip()))


def fetch_latest(repo, token="", opener=None):
    """The newest release: {"version", "tag", "zip_url", "sha_url", "notes"}. Raises UpdateError with a plain reason."""
    if not _valid_repo(repo):
        raise UpdateError("No GitHub repository is set. Type it as owner/name (for example Ben/Starling).")
    url = "https://api.github.com/repos/%s/releases/latest" % repo.strip()
    try:
        with _open(url, token, opener) as answer:
            data = json.loads(answer.read().decode("utf-8"))
    except Exception as error:
        code = getattr(error, "code", None)
        if code == 404:
            raise UpdateError("GitHub has no release for %s yet (or the repository is private and needs a token)." % repo)
        raise UpdateError("Could not reach GitHub: %s" % error)
    assets = {a.get("name"): a for a in data.get("assets", []) if isinstance(a, dict)}
    if ASSET_ZIP not in assets or ASSET_SHA not in assets:
        raise UpdateError("The newest release is missing %s or %s." % (ASSET_ZIP, ASSET_SHA))
    return {"version": str(data.get("tag_name", "")).lstrip("v"), "tag": data.get("tag_name", ""),
            "zip_url": assets[ASSET_ZIP]["browser_download_url"], "sha_url": assets[ASSET_SHA]["browser_download_url"],
            "notes": str(data.get("body") or "")[:2000]}


def _download(url, target, token="", opener=None, progress=None):
    digest = hashlib.sha256()
    total = 0
    with _open(url, token, opener, timeout=60) as answer, open(target, "wb") as out:
        size = int(getattr(answer, "headers", {}).get("Content-Length", 0) or 0) if hasattr(answer, "headers") else 0
        while True:
            chunk = answer.read(256 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_ZIP_BYTES:
                raise UpdateError("The download is far bigger than expected, so I stopped.")
            out.write(chunk)
            digest.update(chunk)
            if progress:
                progress(total, size)
    return digest.hexdigest()


def _safe_extract(archive, folder):
    """Unpack, refusing any file that would land outside the folder."""
    root = Path(folder).resolve()
    with zipfile.ZipFile(archive) as z:
        for member in z.namelist():
            target = (root / member).resolve()
            if not str(target).startswith(str(root)):
                raise UpdateError("The update contains an unsafe file path (%s)." % member)
        z.extractall(root)
    entries = [p for p in root.iterdir()]
    if len(entries) == 1 and entries[0].is_dir() and not (root / "main.py").exists():
        inner = entries[0]                                 # the zip had one top folder: use what's inside it
        for item in inner.iterdir():
            shutil.move(str(item), str(root / item.name))
        inner.rmdir()
    if not (root / "main.py").is_file() or not (root / "core").is_dir():
        raise UpdateError("The download doesn't look like Starling (no main.py / core folder).")


def stage_update(info, updates_dir, token="", opener=None, progress=None):
    """Download + verify + unpack into updates/pending. Nothing live changes. Returns the pending folder."""
    updates = Path(updates_dir)
    pending = updates / "pending"
    shutil.rmtree(pending, ignore_errors=True)
    updates.mkdir(parents=True, exist_ok=True)
    archive = updates / ASSET_ZIP
    try:
        with _open(info["sha_url"], token, opener) as answer:
            expected = answer.read().decode("utf-8", "replace").split()[0].strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise UpdateError("The fingerprint file isn't valid.")
        actual = _download(info["zip_url"], archive, token, opener, progress)
        if actual != expected:
            raise UpdateError("The download doesn't match its fingerprint, so I threw it away.")
        pending.mkdir()
        _safe_extract(archive, pending)
        (updates / "READY.json").write_text(json.dumps({"version": info["version"]}), encoding="utf-8")
    except UpdateError:
        shutil.rmtree(pending, ignore_errors=True)
        raise
    except Exception as error:
        shutil.rmtree(pending, ignore_errors=True)
        raise UpdateError("The download failed: %s" % error)
    finally:
        try:
            archive.unlink()
        except OSError:
            pass
    return pending


def pending_version(updates_dir):
    try:
        return json.loads((Path(updates_dir) / "READY.json").read_text(encoding="utf-8")).get("version")
    except Exception:
        return None


def _copy_keep(old, new):
    for relative in KEEP:
        source, target = Path(old) / relative, Path(new) / relative
        if not source.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)


def apply_pending(app_dir, updates_dir, check=None):
    """Swap the staged version in. Returns the new version, or None if nothing was waiting.

    check: optional function(app_dir) -> bool run on the NEW copy before the swap is final (the launcher passes a
    startup test). If it returns False/raises, the old version is put back and UpdateError is raised.
    """
    app, updates = Path(app_dir), Path(updates_dir)
    pending, version = updates / "pending", pending_version(updates)
    if not pending.is_dir() or version is None:
        return None
    previous = app.with_name(app.name + ".previous")
    try:
        _copy_keep(app, pending)
        shutil.rmtree(previous, ignore_errors=True)
        app.rename(previous)
    except Exception as error:
        raise UpdateError("Couldn't prepare the update (%s). Nothing was changed." % error)
    try:
        pending.rename(app)
    except Exception as error:
        previous.rename(app)                                  # put the old one straight back
        raise UpdateError("Couldn't switch to the new version (%s). The old one is back in place." % error)
    if check is not None:
        try:
            good = check(app)
        except Exception:
            good = False
        if not good:
            failed = app.with_name(app.name + ".failed")
            shutil.rmtree(failed, ignore_errors=True)
            app.rename(failed)
            previous.rename(app)
            shutil.rmtree(failed, ignore_errors=True)
            _clear(updates)
            raise UpdateError("Version %s failed its start-up test, so I went back to the old version." % version)
    _clear(updates)
    return version


def _clear(updates):
    shutil.rmtree(Path(updates) / "pending", ignore_errors=True)
    try:
        (Path(updates) / "READY.json").unlink()
    except OSError:
        pass


def roll_back(app_dir):
    """Manual undo: swap the 'previous' copy back. Returns True if it did."""
    app = Path(app_dir)
    previous = app.with_name(app.name + ".previous")
    if not previous.is_dir():
        return False
    swap = app.with_name(app.name + ".swap")
    shutil.rmtree(swap, ignore_errors=True)
    app.rename(swap)
    previous.rename(app)
    swap.rename(previous)
    return True
