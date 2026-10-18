# Phase 3: STARLING's Voice

STARLING can now speak. Her 437 recordings are installed as the default voice pack,
and anything without a recording is spoken by her cloned Kokoro voice.

## Test 1: the voice test
Double-click **run_voice_test.bat**. It checks each part and plays two things:
1. a recorded Starling line,
2. a sentence in her cloned voice.

At the end it lists the voices installed in Windows. Send me the whole window
if anything says FAILED or NOT available.

## Test 2: the demo, with sound
Double-click **run_demo.bat**. The pretend play session now has sound, with
about two and a half seconds between events. Press Ctrl+C to stop early.

## Test 3: the real game
Double-click **run_starling.bat** and play. Lines the window shows as `says` are
the recordings being played.

## How she decides what to say
- **Critical events** (low fuel, hull damage, shields, interdiction...) go first and
  cut off anything less important. They are never dropped.
- **Ordinary events** wait their turn, but are skipped if they get stale (8 seconds).
- **Low-importance events** are skipped if she is already talking.
- **Cooldowns** stop repeats (for example fuel scooping: once every 3 minutes).
  Change them in `config\speech.json`.
- **No recording?** Ordinary events stay quiet. Critical events are always
  spoken (with her cloned voice if there is no recording).
- **Low fuel** plays her "Warning" recording, then says the fuel percentage.

## Settings you can change (config\settings.json)
    "tts":    { "volume": 100, "rate": 0, "pitch": 0, "voice": "" }
    "speech": { "enabled": true, "use_recordings": true, "allow_mature": false }
    "personality": { "mood": "Friendly" }

- `volume` 0 to 100. `rate` -10 to 10 and `pitch` -10 to 10 : `rate` changes speed; `pitch` is not supported by Kokoro.
- `voice`: the name of a Windows voice (the voice test lists them). Empty = default.
- `allow_mature`: true lets her use the 5 lines with strong language.
- `mood`: try `Friendly`, `Close`, `Sarcastic` or `Frustrated` to hear the
  different line variations. In Phase 6 her mood will change by itself.
- `enabled`: false = silent (she still prints events).

## Where things are
| Path | What |
|---|---|
| `voicepacks\default\audio\` | the 437 mp3 files |
| `voicepacks\default\dialogue.json` | every line, grouped by event and mood |
| `dialogue\core_lines.json` | text-only back-up lines (cloned voice) |
| `config\speech.json` | cooldowns |
| `docs\voice_line_map.csv` | old file name, new file name, text, and where it is used |

## Editing lines
Open `dialogue.json` in Notepad. A key is an event name, optionally followed by
`_Friendly`, `_Close`, `_Sarcastic` or `_Frustrated`. To move a recording to a
different event, copy its entry under another key. A friendly editor arrives in Phase 7.

## Voice providers
| Name | State |
|---|---|
| windows | works (built into Windows, nothing to install) |
| recorded | works (plays your mp3 files) |
| piper, elevenlabs, azure | slots reserved, not built yet |

## Notes
- Recordings play through Windows' built-in media system, so nothing extra is installed.
- Only share the voice pack if you have the right to share the recordings.
- I could not test real Windows sound from my side. The logic is tested with
  stand-in voices, so your voice test is the real check.

---

# Update 2: fixes from the first play session

## What changed
- **Hardpoints are ignored in supercruise and during a jump.** The game flips them
  around every jump; STARLING no longer reports it, and does not announce them late
  when you drop out.
- **Fuel scooping (three call-outs):** "Fuel scooping" when fuel starts flowing,
  "Fuel scooping complete" when the tank is full (once per scoop), and
  "Fuel scoop disengaged" when you leave the scoop (only if you scooped for at
  least 3 seconds). If you leave early, you only hear "disengaged".
- **Jumping:** "Frameshift drive charging" when charging starts, then
  "Four, three, two, one, engage" when the hyperspace jump begins.
  Supercruise jumps no longer play the countdown.
- **Arriving in a system:** no more "Engine engaged". She says "Jump complete."
  (cloned voice until you record the lines listed below).
- **Vehicles:** when you switch vehicle (ship, SRV, on foot, Nomad) STARLING treats it as a
  fresh start. Landing gear and the other ship switches are only read while you
  are in the main ship, and SRV switches only while you are in the SRV.
- **Boarding the main ship** (from the SRV or on foot) plays "Docking complete".
- **Exobiology:** biological signals found, 1st/2nd/3rd sample (with the species name),
  and selling the data.
- **Planned recordings:** lines marked `"planned": true` in dialogue.json are spoken
  with her cloned voice until the mp3 exists.

## Adding the extra recordings
`docs\EXTRA_VOICE_LINES_NEEDED.csv` lists 35 lines: what to record and the exact
file name to save each as.
1. Record the line and save it as an mp3 with EXACTLY that file name.
2. Drop it into `voicepacks\default\audio\`.
3. That's all. Next time STARLING starts she uses it. No editing needed.

## The Nomad
The debug session showed that the game reports the Nomad as an SRV (with ship-like
switches such as landing gear), and the journal says which one it is
(`LaunchVessel`). STARLING now knows when the Nomad is out:
- She says "Launch successful" when you launch it.
- Landing gear, flight assist, lights and night vision are announced while you fly it.
- Weapons, analysis mode and the other ship switches the game flips around it are ignored.
- Stepping out, getting back in, and docking back into the main ship are each
  treated as a fresh start, so nothing is announced in a storm.
- Touchdown and lift-off are announced as before.
`run_debug.bat` is still there if you want to look at anything else the game does.

## Coming later
- **Key binds** (asking her to open the galaxy map) belong to Phase 9, the command mode.
  She will read your game's bindings file, so no setup is needed.
- **Sample distance** for exobiology needs your position on the planet; also later.


## If fuel scooping still sounds wrong
Run `run_debug.bat`, fly to a star, scoop until the tank is full, stay in range
for about 10 seconds, leave, then do one more where you leave before it is full.
Press Ctrl+C and send me `logs\debug_session.txt`. It shows the fuel level and the
scoop switch every second, so I can see exactly when the game changes them.

---

## v5: the cloned offline voice (Kokoro) replaces the Windows "Hazel" voice

**What changed:** if a line has a recording, the mp3 plays exactly as before. If it does not,
the text is spoken by a local AI voice (Kokoro) that has been tuned to sound like your recordings.
Nothing goes online while she speaks. The Windows voice is no longer used.

**Files**
| File | What it does |
|------|--------------|
| `tts\kokoro_voice_setup.py` | One-time tuning. Reads `voicepacks\default\clone\Tetko_Issued_Notice.mp3` and saves `custom_covas.pt`. Skipped if that file exists. |
| `tts\kokoro_tts.py` | The voice itself. Loads in the background, plays at 24000 Hz through `sounddevice`. |
| `tts\providers.py`, `tts\speech_manager.py` | Now route missing-recording text to Kokoro. Priorities, cooldowns and cut-offs are unchanged. |

**First time (do this once)**
1. Copy the new folder over your old one (keep your `logs` and `data` if you like).
2. Double-click `setup.bat` again. It installs the new add-ons (this is a big download, a few GB for torch is possible).
3. Double-click `run_voice_test.bat`. The first run downloads about 350 MB and tunes your recording.
   It can take several minutes. Later starts are quick.
4. Listen: Test 1 is a real recording, Test 2 is the cloned voice. They should sound alike.

**Re-tune the voice:** delete `custom_covas.pt` and start STARLING again.

**Settings** (`config\settings.json`): `tts.clone_reference` (the mp3), `tts.clone_pack` (the .pt file),
`tts.volume`, `tts.rate`. `speech.windows_emergency_voice` is `false`; set it to `true` only if you
want the old Windows voice as a last resort when Kokoro cannot start.

**Be aware**
- Memory use is much higher than the old 200 MB goal while the voice is loaded (the AI model lives in RAM).
- The recording must be 3 to 30 seconds. Yours is slightly longer, so STARLING automatically uses the first 29.5 seconds.
- Only clone a voice you own or have permission to use.
- While the voice is still loading after start-up, a text line waits (up to 45 seconds) rather than being lost.

---

## v6: no more mp3 recordings - everything is spoken by the cloned voice

- The 437 mp3 files are gone from the voice pack. Every line in `voicepacks\default\dialogue.json` is now plain text
  spoken by her cloned voice. Your original recordings are still safe in your original `Starling.zip`.
- The wording was tidied: typos fixed ("Sheilds", "Handbreak", "Anomoly"), things a voice cannot say removed
  (stage directions like "Laugh" or "Giggle"), duplicates merged, warnings made clearer.
  Edit any line in Notepad; she says whatever you write.
- **Speed:** the first time a line is spoken it has to be made (a moment of delay). After that it is remembered in
  `data\voice_cache`, so it plays instantly. To make them all in advance, double-click **`run_build_voice_cache.bat`**
  once (a few minutes). Run it again after you edit lines.
- The cache clears itself automatically if you re-tune the voice (delete `custom_covas.pt`).
- The recording the voice is copied from stays in `voicepacks\default\clone\`. Do not delete it.

---

## v7: countdown rhythm and quieter scanning

- **Jump countdown:** "Four, three, two, one, engage" is now spoken with a beat between each part
  (each number starts about 0.95 seconds after the last). In `dialogue.json` a `||` inside a line means
  "pause for a beat here". You can use it in any line. After editing, run `run_build_voice_cache.bat` again.
- **Scanning:** she no longer says "Scan complete" for every planet and star. She now only speaks for:
  Earth-like worlds, water worlds, ammonia worlds, terraformable worlds, gas giants with life,
  neutron stars and black holes. The lines are under the `Scan_...` keys in `dialogue.json`.
  The honk ("System scan complete") and surface mapping ("Surface scan complete") are unchanged.
- Want her to speak about other bodies too (for example first discoveries)? Tell me what counts as "of interest".

---

## v8: exobiology values, the "third sample" fix, and more variety

**Third sample bug (fixed).** The game sends "Sample" for the 2nd AND the 3rd sample, then "Analyse" after the 3rd.
STARLING now counts the samples herself, so she says first, second, third.

**What she says when a species is finished** (after the third sample and the analysis):
1. "Analysis complete: Bacterium Informem."
2. "It's worth about 8.4 million credits." (or "First footfall bonus! It's worth about ... credits.")
3. "You're carrying 25 million credits of exobiology data."
When you sell, she tells you what you were paid.

**How accurate are the amounts? Please read.**
- The game does not tell any program what a species is worth until you SELL it.
  So STARLING uses a price list in `config\exobiology_values.json`. Those prices are typed in from community
  tables, so some may be wrong or out of date. Edit the file in Notepad if you spot one.
- **She teaches herself:** every time you sell, the game reports the real price of each species. STARLING saves
  these in `data\exobiology_learned.json` and uses them from then on. Real prices always beat the list.
- **First footfall:** when the scanner sees a planet it records whether anyone has stood on it. If not, and you
  sample there, she counts the bonus as 5 x the price (set by `first_footfall_multiplier` in the same file).
  If she never scanned that planet, she does not claim a bonus. Your sale confirms the true total.
- If a species is not in the list she says she has no price yet instead of guessing.
- What you are carrying is remembered between sessions (`data\exobiology_carried.json`). It is emptied when you
  sell, or when you die (the game removes unsold exobiology data when you die).

**More variety.** Most events now have 3 to 6 different wordings, so she repeats herself far less.
Lines you add in `dialogue.json` work the same way. Run `run_build_voice_cache.bat` again after the update.

---

## v9: how far to walk for the next sample

After the FIRST exobiology sample she now says how far away the next one must be, for example:
"First sample collected: Bacterium Informem. The next sample needs to be at least 500 metres away."

The distances are in `config\exobiology_values.json` under `colony_distance_m`, by genus
(Aleoida 150, Bacterium 500, Cactoida 300, Clypeus 150, Concha 150, Electricae 1000, Fonticulua 500, Frutexa 150,
Fumerola 100, Fungoida 300, Osseus 800, Recepta 150, Stratum 500, Tubus 800, Tussock 200, the small plants 100).
Edit any number in Notepad. If a genus is not in the list she just announces the sample without a distance.

Also: the harmless torch/huggingface warnings that appeared when the voice loaded are now hidden.
