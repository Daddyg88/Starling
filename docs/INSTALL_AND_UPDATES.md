# Installing and updating Starling (the one-file way)

## For you (the player)
1. Download **Starling.exe** from your GitHub repository's **Releases** page (the newest release).
2. Put it anywhere (the desktop is fine) and double-click it.
3. The first time it shows a small progress window while it downloads Starling, installs Python 3.12 if you don't have it (no admin rights needed) and installs Starling's add-ons. **The first run takes several minutes** (the voice add-ons are large). After that the dashboard opens.
4. Every later start: it checks GitHub, installs a newer version if there is one (about a second when there isn't), then opens the dashboard.

Where things are: `%LOCALAPPDATA%\Starling` holds `app` (the program, plus your `data`, `config\settings.json`, `logs`, `recordings`), `.venv` (private Python) and `launcher.log` (what the launcher did, look here if something fails).

Your mood, settings, recordings, plugins and logs are carried into every new version. The old version is kept as `app.previous` so you can go back by hand: close Starling, rename `app` to `app.new` and `app.previous` to `app`.

## How an update stays safe
- The download must match its SHA-256 fingerprint or it is thrown away.
- It is unpacked off to the side, never over the running copy.
- The switch is two folder renames: old or new, never half of each.
- The new version is test-started (`main.py --check`) and if that fails the old one is put back.

## For me (publishing a new version)
1. Change `core/version.py` (for example `0.12.0`).
2. Commit, then `git tag v0.12.0` and `git push origin main v0.12.0`.
3. The GitHub Action (`.github/workflows/release.yml`) builds `Starling.exe`, `Starling-app.zip` and its fingerprint, and publishes them as a release. Everyone's Starling.exe picks it up on its next start. (The workflow refuses to run if the tag and `version.py` don't match.)

## Not tested
The exe build, the Windows Python install and the pip install were never run in the sandbox (it is Linux with no PyInstaller). The update engine (download check, fingerprint, safe unpack, swap, rollback) and the launcher logic are tested with fakes. Expect to fix small things on the first real run: send me `launcher.log`.
