# STARLING

An AI ship companion for Elite Dangerous. She watches your journal, speaks up,
remembers you, and (eventually) chats with you.

**Current state: Phase 6 of 10 - she speaks, listens, has moods, a dashboard, voice commands and push-to-talk.**
Double-click `run_dashboard.bat` to open it (see `docs/PHASE5_GUIDE.md` and `docs/MOOD_GUIDE.md`).
Voice commands, push-to-talk and the X52: `docs/PHASE6_GUIDE.md` (try `run_controls_test.bat` first).

## Quick start
1. Read `docs/SETUP_GUIDE.md` (about 5 minutes).
2. Double-click `setup.bat` once, then `run_voice_test.bat` to check her voice (`docs/PHASE3_GUIDE.md`).
3. Double-click `run_demo.bat` to see her react to a pretend session,
   or `run_starling.bat` to watch the real game. See `docs/PHASE2_GUIDE.md`.

## What is where
| Folder | Job |
|---|---|
| `core/` | Shared plumbing: folders, logging, settings, the event bus |
| `database/` | Long-term storage (relationship, memories, stats) |
| `config/` | Settings you can edit (`settings.json`, `events.json`) |
| `journal/`, `events/` | Phase 2: reading the game |
| `tts/` | Phase 3: speaking (done). `stt/` is Phase 4: listening |
| `personality/` | Dialogue and the event speaker (Phase 3); moods in Phase 5 |
| `memory/` | Phase 7: memories (planned) |
| `ui/` | Phase 5: the dashboard |
| `control/` | Phase 6: voice commands, key pressing, push-to-talk, joystick |
| `dialogue/`, `voicepacks/` | Spoken lines and voice packs |
| `logs/` | STARLING's diary and error reports |
| `tests/` | Automatic checks |
See docs/UPDATING.md for how to update without losing settings.
New in 0.15.0: longer chattier lines for everyday events, trip-aware small talk, a livelier chat rate (plus a Chatty setting), and things you can say to her ("how are you?", "tell me a joke", "talk to me"). New in 0.14.0: small talk when it has been quiet (jokes in general, fight talk in combat mode, exploring talk in analysis mode; Personality page > "Small talk"). New in 0.13.0: she announces ship changes, new combat/wing/on-foot speech, dying in a fight costs no mood, wanted kills raise it, wingman and fighter voice commands (docs/COMBAT_GUIDE.md). New in 0.12.1: she no longer speaks or shows key-clash warnings (they are only written to the log). New in 0.12.0: Phase 7 memory - she remembers your records, deaths and big moments, mentions one at login, answers "what do you remember?", and the Memory page lets you read or erase it (docs/PHASE7_GUIDE.md). New in 0.11.6: macros warn when a key they press is also bound to another ship action (like Enter for both UI Select and quick comms). New in 0.11.5: "close all overlays", more ways to say Galnet and colonisation, and she only remembers a mis-hearing when the match is very close. New in 0.11.4: the launcher no longer passes its own Tcl/Tk folders to the dashboard (fixes "Tcl wasn't installed properly"). New in 0.11.3: the launcher now tells you why Starling closed instead of showing nothing. New in 0.11.2: release workflow can add files to a release you made by hand. New in 0.11.1: auto-updater, Starling.exe launcher, GitHub release build (see docs/INSTALL_AND_UPDATES.md). New in 0.11.0: value on the first biology scan (excitement for the top 10, a description on the second), saying thank you, speech learning, new Void Compass overlays picked up automatically, Navigation page buttons, docking without the last Down, mood no longer resets. New in 0.10.9: the plot macro zooms IN for 0.2 s. New in 0.10.8: the plot macro no longer presses Down after the paste. New in 0.10.7: neutron plotting now runs by itself (it was never switched on before): after a route is plotted, and 4 seconds after each supercharge. New in 0.10.6: the plot macro zooms out a little before setting the target. New in 0.10.5: the neutron plot macro follows your recording and starts 3 seconds after the supercharge. New in 0.10.4: the docking macro now follows your own recorded button presses. New in 0.10.3: the recorder recognises sticks Elite names (like SaitekX52). New in 0.10.2: **Record my buttons** (`run_record_buttons.bat`) writes down which HOTAS buttons you press and when, so macros can be built from it. New in 0.10.1: bookmark boxes keep what you type, outlined menu. New in 0.10.0: mood pictures, Bookmarks page (say "plot a neutron route to Home"), space-age dashboard, neutron plotter and galaxy map macro, Void Compass, the Watcher. See docs/PHASE6_GUIDE.md.
