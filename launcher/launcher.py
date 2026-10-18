"""
STARLING LAUNCHER - the program inside Starling.exe.

Double-click it and it does everything, showing one small progress window, then opens the dashboard:
  1. installs the newest Starling from your GitHub releases the first time,
  2. applies any update that was downloaded while Starling was running (and checks for a new one),
  3. makes sure Python 3.12 exists (installs it for you, no admin rights needed),
  4. builds Starling's private environment and installs its add-ons (only when they changed),
  5. starts the dashboard.

Everything lives in  %LOCALAPPDATA%\\Starling   (app\\, updates\\, .venv\\, launcher.log).
Your settings, mood and data live in app\\data and app\\config and survive every update.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import updater                      # noqa: E402  (pure standard library)
from core.updater import UpdateError          # noqa: E402

try:
    from launcher_config import REPO          # noqa: E402
except Exception:                             # pragma: no cover
    REPO = ""

PYTHON_VERSION = "3.12.8"
PYTHON_URL = "https://www.python.org/ftp/python/%s/python-%s-amd64.exe" % (PYTHON_VERSION, PYTHON_VERSION)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# PyInstaller sets these so the exe finds ITS OWN copy of Tcl/Tk (in a temporary folder). Programs we start would
# inherit them and look for Tcl in that temporary folder instead of in their own Python: "Tcl wasn't installed properly".
POISON = ("TCL_LIBRARY", "TK_LIBRARY", "TCLLIBPATH", "TIX_LIBRARY", "PYTHONHOME", "PYTHONPATH", "_MEIPASS2",
          "_PYI_APPLICATION_HOME_DIR", "_PYI_ARCHIVE_FILE", "_PYI_PARENT_PROCESS_LEVEL")


def clean_env(extra=None):
    env = {k: v for k, v in os.environ.items() if k not in POISON}
    env.update(extra or {})
    return env


def install_home():
    override = os.environ.get("STARLING_HOME")
    if override:
        return Path(override)
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Starling"


class Layout:
    def __init__(self, home):
        self.home = Path(home)
        self.app = self.home / "app"
        self.updates = self.home / "updates"
        self.venv = self.home / ".venv"
        self.log = self.home / "launcher.log"
        self.python = self.venv / "Scripts" / "python.exe"
        self.pythonw = self.venv / "Scripts" / "pythonw.exe"
        self.req_mark = self.venv / "requirements.sha256"


def requirements_hash(app):
    try:
        return hashlib.sha256((Path(app) / "requirements.txt").read_bytes()).hexdigest()
    except OSError:
        return ""


def find_system_python():
    """A usable Python 3.10-3.13 that is not our own venv, or None."""
    candidates = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        for minor in ("312", "311", "313", "310"):
            candidates.append([str(Path(local) / "Programs" / "Python" / ("Python" + minor) / "python.exe")])
    candidates += [["py", "-3.12"], ["py", "-3.11"], ["py", "-3.13"], ["python"]]
    for command in candidates:
        if len(command) == 1 and command[0].endswith("python.exe") and not Path(command[0]).exists():
            continue
        try:
            out = subprocess.run(command + ["-c", "import sys;print('%d.%d'%sys.version_info[:2]);print(sys.executable)"],
                                 capture_output=True, text=True, timeout=20, creationflags=NO_WINDOW, env=clean_env())
            lines = out.stdout.split()
            if out.returncode == 0 and lines:
                major, minor = (int(x) for x in lines[0].split("."))
                if major == 3 and 10 <= minor <= 13:
                    return lines[1]
        except Exception:
            continue
    return None


class Launcher:
    def __init__(self, layout, say, repo=REPO, run=subprocess.run, popen=subprocess.Popen):
        self.l, self.say, self.repo, self.run, self.popen = layout, say, repo, run, popen

    def log(self, text):
        try:
            self.l.home.mkdir(parents=True, exist_ok=True)
            with open(self.l.log, "a", encoding="utf-8") as handle:
                handle.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n")
        except OSError:
            pass

    # ---- steps ----
    def startup_test(self, folder):
        """Does the new version start? (python main.py --check). Used to decide whether to keep an update."""
        if not self.l.python.exists():
            return True                      # no environment yet: nothing to test with; it is tested after setup
        self.install_requirements(folder)    # a new version may need new add-ons before it can start
        done = self.run([str(self.l.python), "main.py", "--check"], cwd=str(folder), capture_output=True, text=True,
                        timeout=180, creationflags=NO_WINDOW, env=clean_env())
        self.log("startup test exit %s %s" % (done.returncode, (done.stdout + done.stderr)[-400:].replace("\n", " | ")))
        return done.returncode == 0

    def apply_waiting_update(self):
        try:
            self.say("Installing the downloaded update...")
            version = updater.apply_pending(self.l.app, self.l.updates, check=self.startup_test)
            if version:
                self.log("Updated to %s" % version)
        except UpdateError as error:
            self.log("Update problem: %s" % error)
            self.say(str(error))

    def current_version(self):
        try:
            text = (self.l.app / "core" / "version.py").read_text(encoding="utf-8")
            return text.split('"')[1]
        except Exception:
            return "0"

    def get_newest(self, first_run):
        """Download the newest release if we have none (first run) or a newer one exists. Quiet if offline."""
        if not self.repo:
            if first_run:
                raise UpdateError("This Starling.exe wasn't built with a GitHub repository, so it can't download Starling.")
            return
        try:
            info = updater.fetch_latest(self.repo)
        except UpdateError as error:
            if first_run:
                raise
            self.log("Update check skipped: %s" % error)
            return
        if not first_run and not updater.is_newer(info["version"], self.current_version()):
            return
        self.say("Downloading Starling %s..." % info["version"])
        updater.stage_update(info, self.l.updates,
                             progress=lambda done, total: self.say("Downloading Starling %s... %d%%" % (
                                 info["version"], done * 100 // total if total else 0)))
        if first_run and not self.l.app.exists():
            self.l.app.mkdir(parents=True)               # apply_pending swaps the staged folder over this one
        self.apply_waiting_update()

    def ensure_python(self):
        if self.l.python.exists():
            return
        found = find_system_python()
        if found:
            self.log("Using Python at %s" % found)
            self._base_python = found
            return
        self.say("Installing Python %s (one time, about a minute)..." % PYTHON_VERSION)
        installer = self.l.home / "python-installer.exe"
        with urllib.request.urlopen(PYTHON_URL, timeout=60) as answer, open(installer, "wb") as out:
            shutil.copyfileobj(answer, out)
        done = self.run([str(installer), "/quiet", "InstallAllUsers=0", "PrependPath=0", "Include_test=0",
                         "Include_launcher=0", "Shortcuts=0"], timeout=900, env=clean_env())
        installer.unlink(missing_ok=True)
        found = find_system_python()
        if done.returncode != 0 or not found:
            raise RuntimeError("Python could not be installed automatically. Install Python 3.12 from python.org, then run Starling again.")
        self._base_python = found

    def ensure_environment(self):
        if not self.l.python.exists():
            self.ensure_python()
            self.say("Creating Starling's private environment...")
            done = self.run([self._base_python, "-m", "venv", str(self.l.venv)], capture_output=True, text=True,
                            creationflags=NO_WINDOW, env=clean_env())
            if done.returncode != 0:
                self.log(done.stdout + done.stderr)
                raise RuntimeError("Could not create the environment. See launcher.log.")
        self.install_requirements(self.l.app)

    def install_requirements(self, folder):
        """Installs the add-ons a version needs (only if its requirements.txt changed since last time)."""
        folder = Path(folder)
        wanted = requirements_hash(folder)
        have = self.l.req_mark.read_text().strip() if self.l.req_mark.exists() else ""
        if wanted and wanted != have:
            self.say("Installing Starling's add-ons (the first time takes several minutes)...")
            self.run([str(self.l.python), "-m", "pip", "install", "--upgrade", "pip"], capture_output=True, text=True,
                     creationflags=NO_WINDOW, env=clean_env())
            process = self.popen([str(self.l.python), "-m", "pip", "install", "-r", str(folder / "requirements.txt")],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=NO_WINDOW, env=clean_env())
            tail = []
            for line in process.stdout:
                tail = (tail + [line.rstrip()])[-30:]
                if line.startswith(("Collecting", "Downloading", "Installing")):
                    self.say("Installing add-ons... " + line.strip()[:70])
            if process.wait() != 0:
                self.log("\n".join(tail))
                raise RuntimeError("The add-ons didn't install. Check your internet connection and run Starling again. "
                                   "Details are in launcher.log.")
            self.l.req_mark.write_text(wanted)

    def start_dashboard(self, watch_seconds=25):
        """Starts the dashboard and watches it for a few seconds. If it dies straight away, say why (instead of
        silently showing nothing, which is what a hidden window does)."""
        self.say("Starting Starling...")
        exe = self.l.pythonw if self.l.pythonw.exists() else self.l.python
        extra = {"STARLING_LAUNCHER": "1", "PYTHONUTF8": "1"}
        if self.repo:
            extra["STARLING_REPO"] = self.repo               # so the dashboard's update page knows where to look
        env = clean_env(extra)
        errors = self.l.home / "dashboard_output.txt"
        with open(errors, "w", encoding="utf-8", errors="replace") as out:
            process = self.popen([str(exe), "main.py", "--dashboard"], cwd=str(self.l.app), env=env,
                                 stdout=out, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
        deadline = time.time() + watch_seconds
        while time.time() < deadline:
            code = process.poll() if hasattr(process, "poll") else None
            if code is not None:
                tail = ""
                try:
                    tail = errors.read_text(encoding="utf-8", errors="replace")[-1500:]
                except OSError:
                    pass
                self.log("Dashboard exited with code %s:\n%s" % (code, tail))
                last = [line for line in tail.splitlines() if line.strip()][-6:]
                raise RuntimeError("Starling started but closed straight away (code %s).\n\n%s\n\n"
                                   "The full text is in %s" % (code, "\n".join(last), errors))
            time.sleep(0.5)
        self.log("Dashboard is running.")

    def run_all(self):
        self.l.home.mkdir(parents=True, exist_ok=True)
        first_run = not (self.l.app / "main.py").exists()
        if not first_run:
            self.apply_waiting_update()
        self.get_newest(first_run)
        if not (self.l.app / "main.py").exists():
            raise RuntimeError("Starling isn't installed and couldn't be downloaded.")
        self.ensure_environment()
        self.start_dashboard()


def main():
    layout = Layout(install_home())
    problem = []
    try:
        import tkinter as tk
        from tkinter import ttk
        root = tk.Tk()
        root.title("Starling")
        root.geometry("460x120")
        root.resizable(False, False)
        label = tk.Label(root, text="Starting Starling...", wraplength=430, justify="left")
        label.pack(padx=16, pady=(18, 8), anchor="w")
        bar = ttk.Progressbar(root, mode="indeterminate", length=428)
        bar.pack(padx=16)
        bar.start(12)
        say = lambda text: root.after(0, lambda: label.config(text=text))
    except Exception:
        root, say = None, (lambda text: None)

    launcher = Launcher(layout, say)

    def work():
        try:
            launcher.run_all()
        except Exception as error:
            launcher.log("FAILED: %s" % error)
            problem.append(str(error))
        if root is not None:
            root.after(1200 if not problem else 0, root.quit)

    if root is not None:
        threading.Thread(target=work, daemon=True).start()
        root.mainloop()
        if problem:
            from tkinter import messagebox
            messagebox.showerror("Starling couldn't start", "%s\n\nLog: %s" % (problem[0], layout.log))
        root.destroy()
    else:
        work()
    return 1 if problem else 0


if __name__ == "__main__":
    sys.exit(main())
