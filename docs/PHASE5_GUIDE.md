# Phase 5 - The Dashboard

## Start it
1. Double-click **setup.bat** once more (it installs `customtkinter`, the window library).
2. Double-click **run_dashboard.bat**.

STARLING starts as normal (voice, listening if you turned it on, game watching) and a window opens.
Closing the window stops STARLING.

## The pages
- **Home** - is the voice ready, is she listening, what system you are in, exobiology on board, recent events.
- **Voice** - on/off, volume, speaking speed, a **Voice** drop-down and a **Test her voice** button.
  Voices: Starling's own cloned voice, plus 11 free female and 8 free male Kokoro voices (all offline).
  The first time you pick a new voice it downloads a tiny file (needs internet once). If that fails she
  falls back to her cloned voice. Pick a voice, press **Test her voice** - it changes instantly, no restart.
  Her written lines are tuned for her own voice; other voices say the same words.
- **Listening** - choose your **microphone** from a drop-down, listening quality, sensitivity, her name, wake-word on/off. **Refresh microphone list** re-scans if you plug a headset in.
- **Personality** - mood, voice pack, strong language on/off.
- **Game** - journal folder, log detail.

Volume, speed, mood, strong language, "only react to her name" and "she answers" take effect at once.
Anything marked *(applies after restart)* needs STARLING closed and reopened.
Press **Save settings** (or just close the window - it saves for you).

## Change the look
Open `ui/theme.py`. Every colour, the font and the window size are at the top. Change a `#RRGGBB` and restart.

## Add a setting to the dashboard
Open `ui/settings_model.py`, find the page in `build_pages`, and add one line, for example:

    Field("tts.pitch", "Pitch", "choice", [("Low", -3), ("Normal", 0), ("High", 3)]),

Kinds: `"choice"` (drop-down), `"toggle"` (switch), `"text"` (typed box). The window builds itself from the list.

## Test
`run_tests.bat` - the settings logic is tested (271 tests). The window itself was written without being able
to open it, so if something looks wrong, send me a screenshot or `logs\errors.log`.

## Personality page (new)
- **Style**: *Personality* (banter, moods, pet names) or *Info only* (plain, neutral lines, no jokes).
- **Mood**: Friendly and Close are sweet and cute. Sarcastic and Frustrated are snide - and sweary if **Allow strong language** is on.
- **Extra comments**: how often she tacks a short comment onto a line (Never / Rarely / Sometimes / Often). At most one every 40 seconds.
- **Pet names**: swaps "Commander" for Sweetheart, Darling... (or Genius, Hotshot, and worse in a bad mood).
- **Gets affectionate when rich**: carry more exobiology data than this (default 500 million) and she turns very affectionate.
- Safety warnings (shields, hull, interdiction, overheating, etc.) are never touched by personality.
- All the words are in `voicepacks/default/personality.json` - edit or add your own lines.

## Console warnings
The "huggingface_hub / symlinks / unauthenticated" messages are harmless and are now hidden.

## New name: Starling
The project is now called **Starling**. Her name lives in ONE place: *Personality > Her name* on the dashboard
(or `app.name` in `config\settings.json`). Change it there and her spoken lines, window title and wake word follow.
- The wake word is her name unless you type something into *Listening > Wake word*.
- In dialogue files, `@NAME@` is replaced by her name when she speaks.
- Moving from the old Tetko folder: copy your old `data` folder into the new `Starling` folder (it holds her memory,
  mood, tuned voice and saved sounds), then run `setup.bat` once.

## You are: Male / Female / Not specified
*Personality > You are* changes how she talks TO you, whatever voice she uses.
- Male: handsome, tiger, star-man, space cowboy...
- Female: beautiful, angel, star-girl, space cowgirl...
- Not specified: only neutral names (sweetheart, darling, gorgeous, genius...).
Compliments and affectionate remarks follow the same setting. Extra lines go in `voicepacks\default\personality.json`
under keys ending `_Male` or `_Female` (e.g. `PetName_Cute_Female`).

## Her picture
The Home page shows an illustrated, dark-haired ship companion. To use your own picture, replace
`ui\assets\avatar.png` (portrait shape, about 4:5; a transparent PNG looks best). Needs the `pillow`
package, which `setup.bat` installs.

## Login greeting (new)
When you load into the game she says hello, which ship you are flying, where you are
(in a system, docked at a station, or landed on a planet) and how she feels about you, e.g.
"Welcome back, Commander. We're in the Python called Stardust. We're docked at Jameson Memorial in the
Shinrarta Dezhra system. ... I am still not very happy with you."
- Turn it on/off: *Personality > Greet me when I load the game*.
- *Info only* style gives just the facts (no mood, no pet names).
- Lines are `Login_...` in `voicepacks\default\personality.json` (`{ship}`, `{system}`, `{station}`, `{body}` are filled in).
- She only greets when you load into the game while Starling is running. If you start Starling after the game is
  already loaded, she stays quiet (she reads the old journal silently).
- Landed is detected from the position the game reports when you are not docked; tell me if it says "in the system"
  when you are actually on a planet.
