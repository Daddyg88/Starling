"""Moves Starling's whole install folder (the app, her data, the private Python environment) to another folder or drive,
for example from C: to D:.

Standard library only, because it also runs as a stand-alone helper (a copy of this file is started from the temp folder, with
the PC's normal Python, while Starling is closed, so no file of the old folder is in use).

How a move goes (nothing is deleted until the copy is proven good):
  1. check the target (empty, not inside the old folder, enough room),
  2. copy everything and compare the file count and size with the original,
  3. check the copied private Python still starts (if not, it is thrown away and Starling.exe builds it again),
  4. write the new place into install_location.txt (the note Starling.exe reads to find her),
  5. only then delete the old folder (the note itself stays),
  6. open Starling.exe again.
If anything goes wrong before step 4 the old folder is untouched, the half copy is removed and she starts where she was."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

POINTER_NAME = "install_location.txt"
KEEP_IN_DEFAULT_HOME = (POINTER_NAME, "move_log.txt")
EXTRA_SPACE = 1 << 30                       # keep 1 GB free on the target drive after the copy
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def default_home():
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "Starling"


def pointer_file():
    return default_home() / POINTER_NAME


def gb(number):
    return "%.1f GB" % (number / float(1 << 30))


def current_home(root, environ=None):
    """(home_folder, '') for an installed Starling (home/app/main.py), else (None, why it cannot be moved from here)."""
    environ = os.environ if environ is None else environ
    if environ.get("STARLING_HOME"):
        return None, "The Windows setting STARLING_HOME is on this PC, and it decides where Starling lives. Change that setting instead."
    root = Path(root)
    if root.name.lower() != "app" or not (root.parent / ".venv").exists():
        return None, "This is not the Starling.exe install (it has no app and .venv folders), so there is nothing for me to move. Just move the folder yourself."
    return root.parent, ""


def with_starling_name(path):
    """A folder picked in the Browse window gets a folder called Starling inside it (the same as the first-run question)."""
    path = Path(path)
    return path if path.name.lower() == "starling" else path / "Starling"


def folder_size(path):
    total = 0
    for folder, _dirs, names in os.walk(str(path)):
        for name in names:
            try:
                total += os.path.getsize(os.path.join(folder, name))
            except OSError:
                pass
    return total


def _inside(child, parent):
    child, parent = os.path.normcase(os.path.abspath(str(child))), os.path.normcase(os.path.abspath(str(parent)))
    return child == parent or child.startswith(parent.rstrip("\\/") + os.sep)


def check_target(old, new, size=None, free_fn=None):
    """(True, '') when `new` is a good place for the install now in `old`, else (False, a plain sentence)."""
    old, new = Path(old), Path(new)
    if not new.is_absolute() or not str(new).strip():
        return False, "Choose a full folder, for example D:\\Starling."
    if _inside(new, old):
        return False, "That folder is inside the one Starling is in now. Choose another place, such as a different drive."
    if _inside(old, new):
        return False, "That folder contains the one Starling is in now. Choose another place."
    if new.exists():
        if not new.is_dir():
            return False, "That is a file, not a folder."
        try:
            if any(new.iterdir()):
                return False, "That folder is not empty. Choose an empty or new folder (a folder called Starling is made for you)."
        except OSError as error:
            return False, "I cannot look inside that folder (%s)." % error
    place = new
    while not place.exists():
        if place.parent == place:
            return False, "That drive was not found."
        place = place.parent
    size = folder_size(old) if size is None else size
    try:
        free = (free_fn or shutil.disk_usage)(str(place)).free
    except OSError as error:
        return False, "I cannot read the free space there (%s)." % error
    if free < size + EXTRA_SPACE:
        return False, "Not enough room there: Starling needs %s and that drive has %s free." % (gb(size + EXTRA_SPACE), gb(free))
    return True, ""


def _venv_starts(python):
    try:
        done = subprocess.run([str(python), "-c", "import sys"], capture_output=True, timeout=60, creationflags=NO_WINDOW)
        return done.returncode == 0
    except Exception:
        return False


def _remove_old(old, pointer, keep=KEEP_IN_DEFAULT_HOME):
    """Deletes the old folder; the note that says where Starling is stays if it lives in there. Returns what could not be deleted."""
    old, left = Path(old), []
    keep_here = Path(pointer).parent.resolve() == old.resolve()
    for entry in list(old.iterdir()):
        if keep_here and entry.name in keep:
            continue
        try:
            shutil.rmtree(str(entry)) if entry.is_dir() and not entry.is_symlink() else entry.unlink()
        except OSError:
            left.append(str(entry))
    if not keep_here:
        try:
            old.rmdir()
        except OSError:
            pass
    return left


def move(old, new, pointer, say=lambda text: None, copy_file=shutil.copy2, venv_ok=_venv_starts, size=None):
    """Does steps 1 to 5 above. Returns (ok, sentence). The old folder is only deleted when the copy is good and the note is written."""
    old, new, pointer = Path(old), Path(new), Path(pointer)
    ok, why = check_target(old, new, size=size)
    if not ok:
        return False, why
    say("Counting the files...")
    files, folders, total = [], [], 0
    for folder, dirs, names in os.walk(str(old)):
        rel = os.path.relpath(folder, str(old))
        folders.append(rel)
        for name in names:
            path = os.path.join(folder, name)
            try:
                length = os.path.getsize(path)
            except OSError:
                length = 0
            files.append((os.path.join(rel, name), length))
            total += length
    made_new = not new.exists()
    try:
        new.mkdir(parents=True, exist_ok=True)
        for rel in folders:
            (new / rel).mkdir(parents=True, exist_ok=True)
        done, shown = 0, -1
        for rel, length in files:
            copy_file(str(old / rel), str(new / rel))
            done += length
            percent = int(100 * done / total) if total else 100
            if percent != shown:
                shown = percent
                say("Copying Starling to the new place... %d%% (%s of %s)" % (percent, gb(done), gb(total)))
        say("Checking the copy...")
        copied = [(r, os.path.getsize(str(new / r))) for r, _ in files]
        if len(copied) != len(files) or sum(s for _, s in copied) != total:
            raise OSError("the copy does not match the original")
    except Exception as error:
        shutil.rmtree(str(new), ignore_errors=True)
        if not made_new:
            new.mkdir(parents=True, exist_ok=True)
        return False, "The copy did not work (%s). Nothing was changed: Starling is still where it was." % error
    python = new / ".venv" / "Scripts" / "python.exe"
    note = ""
    if python.exists() and venv_ok is not None and not venv_ok(python):
        shutil.rmtree(str(new / ".venv"), ignore_errors=True)
        note = " Her private Python did not start in the new place, so Starling.exe will rebuild it on the first start (a few minutes)."
        say("Her private Python will be rebuilt...")
    try:
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text(str(new), encoding="utf-8")
    except OSError as error:
        shutil.rmtree(str(new), ignore_errors=True)
        return False, "I could not save the new place (%s). Nothing was changed: Starling is still where it was." % error
    say("Removing the old copy...")
    left = _remove_old(old, pointer)
    text = "Starling now lives in %s.%s" % (new, note)
    if left:
        text += " The old folder %s could not be fully deleted (%d items are in use); you can delete it yourself later." % (old, len(left))
    return True, text


def helper_python():
    """The PC's real Python (not the private one inside the folder being moved, which would be in use)."""
    base = getattr(sys, "_base_executable", "") or sys.executable
    folder = Path(base).parent
    for name in ("pythonw.exe", "python.exe"):
        if (folder / name).exists():
            return str(folder / name)
    return base


def start_move(old, new, launcher_exe="", spawn=subprocess.Popen, script=None, python=None, wait_pid=None):
    """Starts the helper (it waits for this program to close, moves her, then opens Starling.exe). Returns (ok, sentence)."""
    try:
        helper = Path(tempfile.mkdtemp(prefix="starling_move_")) / "move_home.py"
        shutil.copy2(str(script or __file__), str(helper))
        command = [python or helper_python(), str(helper), "--from", str(old), "--to", str(new), "--pointer", str(pointer_file()),
                   "--wait-pid", str(os.getpid() if wait_pid is None else wait_pid)]
        if launcher_exe:
            command += ["--launch", str(launcher_exe)]
        flags = (0x08000000 | 0x00000008) if sys.platform == "win32" else 0
        spawn(command, creationflags=flags, close_fds=True)
    except Exception as error:
        return False, "I could not start the move (%s). Nothing was changed." % error
    return True, "Starling is closing to move to %s. A small window shows the progress; she opens again by herself." % new


def _wait_for_exit(pid, seconds=60):
    if not pid or sys.platform != "win32":
        time.sleep(3)
        return
    import ctypes
    handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, int(pid))        # SYNCHRONIZE
    if handle:
        ctypes.windll.kernel32.WaitForSingleObject(handle, int(seconds * 1000))
        ctypes.windll.kernel32.CloseHandle(handle)
    time.sleep(2)                                                                    # her speech and chat engines finish closing


def _log(pointer, text):
    try:
        folder = Path(pointer).parent
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / "move_log.txt", "a", encoding="utf-8") as handle:
            handle.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n")
    except OSError:
        pass


def main(argv=None):
    options = argparse.ArgumentParser()
    options.add_argument("--from", dest="old", required=True)
    options.add_argument("--to", dest="new", required=True)
    options.add_argument("--pointer", required=True)
    options.add_argument("--wait-pid", default="0")
    options.add_argument("--launch", default="")
    args = options.parse_args(argv)
    result = []
    window = label = None
    try:
        import tkinter as tk
        from tkinter import ttk
        window = tk.Tk()
        window.title("Moving Starling")
        window.geometry("500x130")
        window.resizable(False, False)
        label = tk.Label(window, text="Waiting for Starling to close...", wraplength=470, justify="left")
        label.pack(padx=16, pady=(18, 8), anchor="w")
        bar = ttk.Progressbar(window, mode="indeterminate", length=468)
        bar.pack(padx=16)
        bar.start(12)
    except Exception:
        window = None

    def say(text):
        _log(args.pointer, text)
        if window is not None:
            window.after(0, lambda: label.config(text=text))

    def work():
        _wait_for_exit(args.wait_pid)
        ok, text = move(args.old, args.new, args.pointer, say=say)
        _log(args.pointer, ("DONE: " if ok else "FAILED: ") + text)
        result.append((ok, text))
        if args.launch and os.path.isfile(args.launch) and (ok or Path(args.old).exists()):
            try:
                subprocess.Popen([args.launch], creationflags=(0x00000008 if sys.platform == "win32" else 0), close_fds=True)
            except OSError:
                pass
        if window is not None:
            window.after(0, window.quit)

    if window is not None:
        threading.Thread(target=work, daemon=True).start()
        window.mainloop()
        try:
            from tkinter import messagebox
            ok, text = result[0] if result else (False, "The move was interrupted.")
            messagebox.showinfo("Starling moved", text) if ok else messagebox.showerror("Starling was not moved", text)
        except Exception:
            pass
        window.destroy()
    else:
        work()
    return 0 if result and result[0][0] else 1


if __name__ == "__main__":
    sys.exit(main())
