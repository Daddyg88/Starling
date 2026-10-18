# STARLING Setup Guide (Windows)

You only do this once.

## 1. Check Python 3.12
Open Command Prompt (Start menu, type `cmd`) and type:

    py -3.12 --version

You should see `Python 3.12.x`. If not, see TROUBLESHOOTING.md.

## 2. Put STARLING in a folder
Unzip `Starling.zip` somewhere easy, for example:

    C:\Starling

Avoid folders that sync to the cloud (OneDrive) and avoid Program Files.
After unzipping, you should see files like `main.py` and `setup.bat` directly
inside `C:\Starling` (not inside another `Starling` folder inside it).

## 3. Run setup (one time)
Double-click `setup.bat`. A black window appears, creates STARLING's private
Python environment (a hidden `.venv` folder), and says
"Setup finished". Press any key to close it.

## 4. Start STARLING
Double-click `run_starling.bat`. You should see:

    ==============================
      STARLING is online.
    ==============================

followed by "Watching: ..." (your Elite Dangerous journal folder).
Press Ctrl+C to stop her. No game running? Use `run_demo.bat` instead
(see PHASE2_GUIDE.md).

New files will appear:
- `data\tetko.db` (her memory)
- `logs\starling.log` (her diary)

## 5. Run the self-checks (optional but recommended)
Double-click `run_tests.bat`. At the bottom you should see:

    Ran 151 tests ... OK

If anything says FAILED, copy the text and send it to me.

## Updating later
When I give you a new version, copy your `data` folder somewhere safe first
(that is STARLING's memory), unzip the new version, then copy `data` back in.
A full update guide comes in a later phase.
