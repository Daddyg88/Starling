# Phase 4: Hearing (speech to text)

STARLING can now listen through your microphone. In this phase she only learns to HEAR and understand you.
Doing things when you ask (opening the galaxy map, checking fuel) and real conversation come in later phases.

## What she does now
- You say her name alone ("Starling?")  ->  she answers ("Yes, Commander?").
- You say her name and a request ("Starling, open the galaxy map")  ->  she says she can't do that YET.
- You talk without her name  ->  she ignores you (so she doesn't react to everything you say).
- She does not listen while she is speaking, so she never hears herself.
- Listening is OFF unless you ask for it, to protect your game's performance.

## First time
1. Unzip `Starling_Phase4.zip` over your folder.
2. Double-click `setup.bat` again (it installs `faster-whisper`, the listening engine).
3. Double-click **`run_listen_test.bat`**. The first time it downloads a small listening model (about 75 MB).
   It lists your microphones, then for 45 seconds shows what she hears. Say "Starling" and a few sentences.
4. If it works, start her with **`run_starling_listening.bat`** instead of `run_starling.bat`.
   (Or set `"enabled": true` under `"stt"` in `config\settings.json`, then `run_starling.bat` listens too.)

## Settings (`config\settings.json`, under `"stt"`)
| Setting | Meaning |
|---|---|
| `enabled` | `true` = listen whenever STARLING starts |
| `model` | `tiny.en` (fastest, default), `base.en` (more accurate, slower, bigger) |
| `microphone` | part of the microphone's name, or its number from the listening test. Empty = Windows default |
| `wake_phrase` | the name she waits for. Default `Starling` |
| `require_wake` | `true` = only react when you say her name |
| `reply` | `false` = hear you but say nothing back |
| `energy_threshold` | 0 = automatic. If she misses quiet speech or reacts to noise, try a number like 0.02 |

## How it is built (for the curious)
- `stt\vad.py` finds where your sentences start and end by loudness (it learns the room's background noise).
- `stt\faster_whisper_stt.py` turns each sentence into text, offline, on 2 CPU threads so the game keeps its speed.
- `stt\wake.py` spots her name even when it is spelled oddly ("Tet co", "Tedko").
- `stt\listener.py` joins it all up and announces what you said on the event bus as `voice.heard`.
- `personality\voice_replies.py` decides what she says back.
- Whisper and Windows speech recognition have empty slots in `stt\` for later.

## Please know
- **Memory/CPU:** listening adds roughly 300 to 500 MB of RAM while the model is loaded (my estimate, not measured),
  and a short burst of CPU each time you speak. This is on top of the cloned voice, so your total RAM use is well
  above the original 200 MB goal. Turn listening off if the game stutters.
- Your words are NOT saved anywhere in this phase.
- English only (the `.en` models).
- Nothing was heard on a real microphone by me; the listening logic is tested with recorded test sounds, so your
  first test on your own microphone is the real check.
