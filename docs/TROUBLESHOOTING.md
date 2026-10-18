# Troubleshooting

## "Could not find Python 3.12" when running setup.bat
Open Command Prompt and type `py -3.12 --version`.
- If it says "No suitable Python runtime found", install Python 3.12 from
  python.org (older releases list) and tick **Add python.exe to PATH**.
- Then run `setup.bat` again.

## "Please double-click setup.bat first"
`run_starling.bat` could not find the `.venv` folder. Run `setup.bat` first, and
check you unzipped everything (do not run files from inside the zip).

## The window closes before I can read it
Use `run_starling.bat` (it waits for a key press) rather than running `main.py`
directly.

## "STARLING could not start"
Open `logs\errors.log` and send me its contents.

## Windows SmartScreen warns about the .bat files
They are plain text files you can open in Notepad to read. Click
"More info" then "Run anyway" if you are happy with what they contain.

## Start fresh
Close STARLING and delete `data\tetko.db`. A new empty memory is created
next time. (This erases her memories, so only do it on purpose.)

## The cloned voice (Kokoro) is silent or will not start
- Run `run_voice_test.bat` and read the Test 2 message.
- "recording was not found": put your mp3 at `voicepacks\default\clone\Tetko_Issued_Notice.mp3`.
- "inno-kokoro is not installed" / "torch is not installed": run `setup.bat` again and read its output for errors.
- Download problems on first run: the model comes from huggingface.co. Check your internet, then retry.
- Sounds wrong after changing the mp3: delete `custom_covas.pt` and restart so she re-learns it.
- Still stuck: send me `logs\errors.log`.

## She does not hear me (listening)
- Run `run_listen_test.bat` and read the top part: it lists your microphones and says if the listening engine is ready.
- "faster-whisper is not installed": run `setup.bat` again.
- She "heard nothing": your Windows default microphone may be the wrong one. Put part of its name (or its number from
  the list) into `config\settings.json` under `"stt"` > `"microphone"`. Also check it is not muted in Windows sound settings
  and that Windows allows apps to use the microphone (Settings > Privacy > Microphone).
- She mishears her name: say it clearly, or change `wake_phrase`; she accepts close spellings.
- She reacts to background noise or misses quiet speech: set `energy_threshold` (try 0.02).
- The game stutters while she listens: set `"enabled": false` under `"stt"`, or use `run_starling.bat` (no listening).
