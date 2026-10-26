# Phase 6 - Voice commands, push-to-talk and your X52

You can now tell her what to do, in everyday language, and she presses **your own** Elite Dangerous key.

> "Starling, lower the landing gear."  >  *presses your landing gear key*  >  "Lowering the landing gear, Commander."

## What is new

| Thing | Where |
|---|---|
| Voice commands (about 45 actions, 1,500+ ways of saying them) | `control/catalog.py` |
| Finds your key from Elite's controls file | `control/binds.py` |
| Presses the key (only while Elite is in front) | `control/sender.py` |
| Push-to-talk (hold or toggle) | `control/ptt.py` |
| Keyboard / mouse / joystick (X52) buttons | `control/inputs.py` |
| Dashboard **Controls** page | `ui/settings_model.py`, `ui/dashboard.py` |
| What she says back | `voicepacks/default/commands.json` |

No new programs to install. Double-click **setup.bat** is not needed again, but harmless.

## Try it in 5 minutes (nothing is pressed in the game)

1. Unzip over your old Starling folder (say yes to replace).
2. Start Elite Dangerous at least once (so the controls file exists) and set your keys as you like.
3. Double-click **run_controls_test.bat**. It shows:
   - your controls file and which commands have a **keyboard** key,
   - your joysticks (the X52 is marked),
   - every key/button you press for 15 seconds (use this to pick a push-to-talk button),
   - a prompt where you type a sentence and see what she *would* do.
4. Double-click **run_dashboard.bat** and open the **Controls** page.

## Using it for real

1. Dashboard > **Listening**: turn on *Listen when the app starts* and pick your microphone. Restart the app.
2. Start Elite Dangerous and stay in the game window.
3. Say *"Starling, open the galaxy map"* (or use push-to-talk below and skip her name).

She only presses keys while the **Elite Dangerous window is the one in front**. If you are looking at your browser she says so and presses nothing. (Setting *Only press keys while Elite is in front*. Leave it on.)

## Things you can say

Anything natural. A few of the many ways:

- **Maps:** "open the galaxy map", "pull up the star map", "show me the system map", "close the galaxy map"
- **Landing gear:** "lower the landing gear", "drop the gear", "wheels down", "gear up", "retract the undercarriage"
- **Weapons:** "deploy hardpoints", "arm weapons", "weapons away", "stand down"
- **Lights etc.:** "turn the lights on", "lights off", "night vision on", "go dark" (silent running), "flight assist off"
- **Targeting:** "target next hostile", "next enemy", "target the highest threat", "target next system", "target wingman two", "next subsystem"
- **Ship:** "deploy a heat sink", "use a shield cell", "fire chaff", "boost", "deploy the cargo scoop"
- **Throttle:** "full stop", "half throttle", "set throttle to seventy five", "full throttle"
- **Panels:** "open the comms panel", "left panel", "role panel", "open the FSS", "open the codex"
- **Hyperspace jump:** say **"engage jump"** (also "jump", "initiate the jump", "make the jump", "jump to hyperspace"). It always presses your **Hyperspace** key.
  For supercruise say **"engage supercruise"**.
- **Two at once:** "lower the landing gear and open the galaxy map"

Politeness and filler are ignored ("could you please...", "Commander", "the", "my").
A slightly mis-heard word still works ("galaxy mat"), but she **never guesses** between opposites: a garbled "raise/lower", "open/close", "on/off" or "next/previous" is refused rather than risked.

### She no longer says things twice

Opening the galaxy map used to give you her confirmation and then the game's own "galaxy map opened" line. Now, after she does
something for you, she stays quiet about the matching game event (once, for about 6 seconds). If you press the key yourself she
still announces it as before. Warnings are never skipped.

### She will not do the wrong thing

- If the gear is **already down** and you say "lower the gear", she says so instead of toggling it back up. (This uses `Status.json`. Until the game has written it, she just presses the key.)
- If a command has **no keyboard key** she tells you which one, and what to do.
- If it is **only bound to a joystick button**, she tells you: she can press keyboard keys only. Bind a spare keyboard key to it as well (Elite lets one action have a primary *and* a secondary).
- The same command heard twice in a second is pressed once.
- Eject cargo and self-destruct are deliberately **not** included.

## Push-to-talk

Dashboard > **Controls**:

1. **Push-to-talk**: choose *Hold the button while I talk* or *Press once to start, again to stop*.
2. Press **Learn push-to-talk button**, then press a key, mouse side button, or a joystick button within 6 seconds.
3. **Save settings**. It applies straight away (no restart).

While push-to-talk is on you **don't need to say her name**: the button means "I'm talking to you". A short beep tells you the microphone opened (switch off with *Beep when the microphone opens*). If you prefer to keep saying her name even with push-to-talk, turn off *No need to say her name with push-to-talk*.

**Pick a button the game does not use.** The button still reaches Elite. Good choices: a spare X52 button, a mouse side button, F13-F24, Scroll Lock.

## Your X52

Windows shows the X52 as a game controller. STARLING finds it by its USB id/name and reads its buttons with the joystick service built into Windows (nothing to install).

- Controls page > **Look for my joystick** lists what she sees. The X52 is tagged.
- Use **Learn** and press any X52 button. It is stored like `joy:06A3:075C:7` (device id + button number).

Honest limits:

- Windows can report **32 buttons per device**. The X52 has more if you count its Mode shifts; those extra "shifted" buttons may not be visible. Pick one of the first 32 (Learn only ever finds those).
- The X52 Pro is two USB devices (stick and throttle); each has its own list. Learn handles that.
- I could not test with a real X52. If Learn doesn't see your button, run **run_controls_test.bat**, press it, and tell me what it prints.
- If your X52 buttons are mapped to keyboard keys by the Saitek/Logitech profile software, you can simply use that key as the push-to-talk button.

## Settings (config\settings.json)

```json
"commands": { "enabled": true, "confirm": true, "require_game_focus": true, "disabled": [] },
"ptt":      { "mode": "off", "button": "", "beep": true, "skip_wake": true }
```

- `commands.disabled` is a list of command ids to switch off, for example `["hyperspace", "supercruise"]` (an id is the first item of each entry in `control/catalog.py`, such as `"gear"`).
- `ptt.mode` is `off`, `hold` or `toggle`.
- `ptt.button` looks like `key:F13`, `mouse:X1` or `joy:06A3:075C:7`.

## Adding a command or a phrase

Open `control/catalog.py`. Each command is one `C(...)` entry. To add a phrase, add a line to its `on=[...]`, `off=[...]`, `toggle=[...]` or `press=[...]` list. Templates use `(a|b)` for choices and `[the]` for optional words; `{OPEN_V}` and friends are shared verb lists at the top of the file. The action name (second item) is the element name in your `.binds` file. Run `run_tests.bat` after editing: it checks that no sentence belongs to two commands.

## What I could not test

I built and tested this without Windows, Elite Dangerous or a joystick, so these are tested only with stand-ins:

- the real key press (`SendInput`) and the "Elite is in front" check,
- reading the X52 through Windows,
- the exact names in your controls file (I used Elite's documented element names; a few punctuation key names such as `Key_SemiColon` are my best reading of the format and are accepted in several spellings).

If a key name is not known, she says "I don't know the key bound to ..." and the log names it, so it is a one-line fix in `control/keys.py`.

If something doesn't work, run **run_controls_test.bat** first. It shows what she can see.

## Added after the first test

- **"Engage jump"** is the hyperspace jump only. `control/catalog.py`, command `hyperspace`.
- **No double speech** for things she did herself (`control/echo.py`).
- **Fifth mood: Neutral**, swearing lines in every mood, and the **"Flirty and naughty when she's very happy"** switch. See `docs/MOOD_GUIDE.md`.
- Her lines for commands live in `voicepacks/default/commands.json`; each mood has its own set (`CommandDone_Neutral` and so on).


## Keeping your settings
See `docs/UPDATING.md`: updates no longer overwrite `config/settings.json`.

## Auto honk
When you arrive in a new system she can hold your fire button for about 6 seconds. If your Discovery Scanner is on that button, that is the "honk".

1. Open the dashboard, **Controls** page, **Auto honk when I arrive in a system**.
2. Choose **Primary fire button** or **Secondary fire button**, whichever your Discovery Scanner is on. (**Off** is the default.)
3. In Elite, make sure the fire group holding your Discovery Scanner is the one selected.

How it works and what to know:
- She finds the key in your Elite controls file, the same way voice commands do.
- It needs a **keyboard key** bound to that fire button. If yours is only on the X52 stick, Elite lets you add a second (keyboard) binding in the controls menu. If she can't find one, she tells you once.
- She never honks while your hardpoints are deployed (so she can't shoot by accident), and only while Elite is the window in front.
- Optional tuning in `config/settings.json`: `autohonk.hold_seconds` (default 6) and `autohonk.delay_seconds` (default 2, the wait after arriving).

## Jump announcements
The old "four, three, two, one, engage" lines are gone. She now says things like "Jumping to Colonia." using the destination system's name.

## Macros: "request docking" and "deploy the Nomad"
Elite has no single key for these, so each one is a **macro**: a list of key presses and pauses, using the keys from YOUR Elite controls.

Say: "request docking", "ask for docking permission", "can I dock", "deploy the Nomad", "launch the Nomad"...

- **Request docking** presses: left panel focus key, wait 0.3 s, Next Tab twice, wait 0.2 s, Select, Down, Select, wait 0.2 s, then the left panel focus key again to close it. Needs keyboard keys for Focus Left Panel, Next Panel/Tab, UI Select and UI Down.
- **Deploy Nomad** looks down at the helm (bottom / role) panel, presses down once, right once, then Select.
- She needs a **keyboard key** bound in Elite for every action the macro uses (panel keys, UI Select, UI Back, UI Up/Down/Left/Right, Previous/Next Panel).

Write your own steps like this (put it in settings.json next to the other sections):

    "macros": {
      "deploy_nomad": ["FocusRightPanel", "wait 0.8", "CyclePreviousPanel", "UI_Down x2", "UI_Select"],
      "request_docking": ["FocusLeftPanel", "wait 0.9", "UI_Select"]
    }

A step is an Elite action name, `Name x3` to press it three times, or `wait 0.5` to pause. Use **Check my keys** and **Try a command** (Controls page) to see what she would do without pressing anything.

## Questions, facts and valuable finds (new in 0.9.4)
She can now ask you things out loud and listen for **yes** or **no**. **Listening must be on** (she can't hear answers otherwise, so she simply doesn't ask).
You can answer in many ways: "yes", "yeah go on", "sure", "why not", "no thanks", "nah", "maybe later", "not now"... With or without her name.

**Facts ("I've been doing some reading...")**
- When you arrive in a system she may ask if you want to hear something interesting. Say yes and she tells you a fact (Elite lore, real space and the galaxy, planet and star types: 249 facts, never repeated until she has told you them all).
- You can also say "Starling, tell me a fact" at any time.
- Dashboard: **Chat and facts** page. Choose how often (Never / Rarely / Sometimes / Often / Very often) and what the topics are.
- Mood: yes = a little better. No = nothing, but turning her down three times in a row costs a little (and she asks less often after that). Not answering = counts as a no and costs a little.

**Valuable planets** ("That one's worth a bit. Shall we go and scan it?")
- Earth-like worlds, water worlds, ammonia worlds, terraformable worlds and rare gas giants that nobody has mapped yet.
- Yes = a small mood boost. No = nothing. Saying nothing = costs a little.

**Life** ("Shall we go and see what's down there?")
- When a world with biological signals is found she wonders aloud. She does **not** wait for a yes or no, and it never changes her mood (it was getting repetitive). Switch it off on the Chat and facts page if you like.

All of these use the usual soft caps (each repeat counts for less, and there is an hourly limit), so her mood can't swing wildly.
She never asks during a safety warning or while your weapons are out. Both prompts can be switched off on the Chat and facts page.

## Paintwork
Elite does not write the paint condition to the journal, so Starling **estimates** it: after about 150 jumps since your last repaint she treats the paint as worn (below 80%), and her mood slowly drains while you play (never below -20). When you pay for a repaint, she gives back **exactly what was lost**. "Repair all" does not fix paint in the game, so it doesn't count here either. Change the jump count in `config/mood_rules.json` (`paint_worn_after_jumps`).

## Other changes in 0.9.4
- Many more lines when you arrive in a system, drop out of supercruise or set off on a jump.
- She says "bloody" much less. Lots of lines were rewritten.
- Friendly mood now also gets the cheeky innuendo (when the "Flirty and naughty" switch is on), a bit less often than Close. There are many new funny lines.
- Request docking now uses your steps: left panel, right twice, down once, right, select, wait, back twice.

## Dark humour and rude innuendo (0.9.5)
- **Dark humour** (Personality page, on by default): about one remark in five is gallows humour, in every mood, with extra lines for each mood. Never during safety warnings.
- **Flirty and naughty** now also works in bad moods: when she is Sarcastic or Frustrated the innuendo turns grumpy and rude ("All thrust and no finesse"). The stronger ones need strong language switched on.

## Void Compass overlays by voice (0.9.6)
Starling talks to **Void Compass** (the overlay app) through its own Local API. No keys are pressed, and Elite does not need to be in front.

**Set up Void Compass once (about a minute)**
1. Open Void Compass, then **Settings > Integrations > Local API** and switch **Local API** on. It says LISTENING.
2. Leave **Allow control** on (it is on by default). With it off, Starling can't change anything and tells you so.
3. If you changed the port, put the same number on Starling's Controls page ("Void Compass Local API port"). Out of the box it is 7380.

**What you can say** (start with her name, as usual)
- "Show the cargo overlay", "hide the navigation HUD", "toggle the galaxy minimap", "turn on the music player".
- "Hide all overlays" / "show all overlays" (the same as Void Compass's hide-all hotkey).
- All 21 overlays work: navigation, survey, heartbeat (the Watcher), notifications, achievements, cargo, carrier, prospector, planet materials, powerplay, gravity warning, station, Galnet ticker, music player, contact scope, jump info, construction needs, trade route, galaxy minimap, postcards and planet waypoint.
- For names that also mean something in the ship (navigation, cargo, station, survey, music...) say "overlay" or "HUD" too, so "show navigation" still opens your left panel as before.
- If it is already on, she says so rather than flipping it off by mistake. If everything is hidden she tells you to say "show overlays".

**Switch it off:** Controls page, "Control Void Compass overlays by voice".
**New Void Compass overlay later?** Add one line to `control/vc_overlays.py`.

**Not tested against the real app:** I wrote this from Void Compass's published API notes (version 5.5.8) and tested it with a pretend Void Compass. If a command says it can't reach Void Compass, check step 1 above.

## The Watcher (0.9.7)
The Watcher is the glowing orb in Void Compass. If you switch his voice on (Void Compass: The Watcher > VOICE), Starling now reacts to him.

**She answers him in her mood**
- Close and Friendly: kind and supportive ("Beautifully put, Watcher. Never change.").
- Neutral: short and businesslike ("Noted, Watcher.").
- Sarcastic and Frustrated: she tells him to be quiet ("Shut up, Watcher."). With strong language switched on, the angriest lines get ruder.
- About 100 lines in `voicepacks/default/watcher.json`. Dashboard, Controls page: switch it off, or choose how often she answers (Every time / Often / Sometimes / Never).

**He waits for a calm moment**
If the Watcher starts talking while she is speaking, while she is waiting for your yes/no, just after a safety warning, or while your weapons are out, you are in danger or being interdicted, your FSD is charging or jumping, you are overheating or low on fuel, she stops him straight away. When things are calm he says it again, and she answers him after. A line still waiting after 3 minutes is dropped because it would be out of date. Switch this off with "Make the Watcher wait for a calm moment".

**Things to know**
- It needs Void Compass's Local API on (see the overlay section above) and his voice switched on and downloaded.
- Void Compass only tells Starling after he has started talking, so at a bad moment you may hear the first word or two before she cuts him off.
- Not tested against the real Void Compass, only with a pretend one.

## Neutron route plotter (0.9.8)
Say **"Starling, plot a neutron route to Colonia"** and she works out the route and keeps track of it as you fly.

**How it works**
- The route comes from **Spansh** (spansh.co.uk), the free community route planner. EDCoPilot is closed-source, so its code could not be copied; this uses Spansh directly, which is what such tools use anyway. You need an internet connection when plotting.
- Spansh gives a list of **waypoints**, mostly neutron stars, and how many normal jumps lie between them.
- **Elite does not let any program plot a route inside the game.** So Starling copies the next waypoint's name to your **clipboard**. In the galaxy map: click the search box, press Ctrl+V, Enter, then plot. She does this again every time you reach a waypoint.
- She tells you when you reach a neutron star ("supercharge, then head for ...") and how many jumps to the next waypoint.
- The route is saved in `data/neutron_route.json`, so it survives a restart.

**What you can say**
- "Plot a neutron route to Colonia" (also Sol, "the bubble", Sagittarius A star, Beagle Point, or any system name).
- "Plot a neutron route to my destination" uses the Destination box on the **Navigation** page.
- "Where's the next waypoint?" says it again and copies it again.
- "How far is left?" gives jumps and neutron stops remaining.
- "Replot the route" works out a fresh route from where you are now.
- "Cancel the route".

**Settings (Navigation page)**
- **Jump range:** leave at 0 and she uses your ship's range from Elite, reduced by the safety margin (Elite's figure is for an empty ship). Type your own laden range if the route fails or is too ambitious.
- **Route style** and **Neutron boost** are Spansh's options. Leave the boost on Normal unless you know your ship gets x6.
- Your own short names for places: in `config/settings.json` add `"neutron": { "favourites": { "home": "Shinrarta Dezhra" } }`.

**Honest limits**
- Not tested against the real Spansh or on Windows: I could not reach Spansh from my workspace, so the Spansh calls follow how other tools use it and were tested with a pretend one. If plotting fails, the log (`logs/`) and what she says will show why.
- A microphone is poor at unusual system names. She says the name she found; say "cancel the route" if it is wrong, or type a destination into the Navigation page.
- She follows waypoints only. The jumps in between are the normal in-game route you paste.

## Hands-free galaxy map plotting (0.9.9)
Say **"Starling, plot the next waypoint"** and she does the galaxy map for you, using your own keys:

1. Fills your clipboard with the next waypoint's name.
2. Opens the galaxy map (your GalaxyMapOpen key), waits 1.5 seconds.
3. Presses your **UI Up** key to reach the search box, then **UI Select** to click into it.
4. Presses Ctrl+V to paste the name, then Enter.
5. Waits 3 seconds for the map to fly there, presses **UI Select** to pick the system.
6. **Holds UI Select** for 1.5 seconds to set it as your route.
7. Closes the galaxy map.

**Switch on "Plot each waypoint in the galaxy map for me"** (Navigation page) and she does this by herself: once when the route is made, then after each neutron supercharge (or on arrival at a fuel stop). Only once per waypoint, and never while your weapons are out, your FSD is charging, or you are in danger, interdicted, overheating or low on fuel.

**IMPORTANT: the sequence is a starting point.** I could not test it against the real galaxy map, and the galaxy map's keyboard behaviour is fiddly. You need keyboard keys for GalaxyMapOpen, UI Up and UI Select in Elite's controls. If it doesn't work first time, **edit the steps**; nothing else needs to change. In `config/settings.json`:

```
"macros": {
  "plot_waypoint": ["GalaxyMapOpen", "wait 2.0", "UI_Up", "wait 0.5", "UI_Select", "wait 0.5", "paste", "wait 0.5", "enter",
                    "wait 4.0", "UI_Select", "wait 1.0", "hold UI_Select 1.5", "wait 1.0", "GalaxyMapOpen"]
}
```
Steps you can use: any Elite action name (`UI_Up`, `UI_Down x3`), `wait 1.5` (seconds), `hold UI_Select 1.5`, `paste` (Ctrl+V) and `enter`. Common fixes: lengthen a wait (the map is slow on your PC), add a `UI_Up` or `UI_Down`, or change which step holds Select. Say "Starling, plot the next waypoint" to test one step at a time.

Notes: if the galaxy map is already open when it starts, the first and last step will toggle it the wrong way round. It only works while Elite is the window in front, like every key command.

## New look, mood pictures and bookmarks (0.10.0)
**Her picture follows her mood.** The Home page shows a picture that matches how she feels, in a frame that changes colour with the mood (pink Close, green Friendly, cyan Neutral, amber Sarcastic, red Frustrated).
- Close uses the blowing-a-kiss picture, Friendly the smiling one, and **Neutral plus the bad moods (Sarcastic and Frustrated) use the serious one**.
- The pictures are in `ui/assets/portraits/`, named after the mood. To give a mood its own picture, drop a file called `Sarcastic.png` (or `Frustrated.png`, `Close.jpg`...) in that folder and reopen the dashboard. A mood with no picture of its own uses Neutral. Any shape works.
- When you update Starling from a new zip, copy your own pictures back into that folder if the update replaces it.

**Bookmarks page.** Eleven boxes: **Home** and **Bookmark 1 to 10**. Type a system name in each (or press **Here** to fill it with the system you are in), then Save settings.
- "Starling, plot a neutron route to **Home**" or "...to **bookmark 3**".
- "Starling, **save this system as bookmark 3**" (or "set home to here") stores the system you are in, with no typing. It appears in the box straight away.
- A bookmark that is empty gets a friendly "bookmark 5 is empty" instead of a route.
- Your bookmarks live in `config/settings.json` under `bookmarks`, so they survive updates.

**Cleaner, space-age dashboard.** Deep-space colours, a cyan instrument-panel header, menu icons, framed cards and a tidier Home page (her picture on the left, status and recent events on the right). Change any colour in `ui/theme.py`.

I could not open the window itself in my workspace, so the drawing is tested with a pretend window library rather than by eye. If something looks off (spacing, a symbol that shows as a box, a font that isn't there), tell me what you see and I will fix it.

## Fix in 0.10.1
- **Bookmarks boxes no longer wipe what you type or paste.** The page refreshed once a second to show bookmarks saved by voice, and it put the old saved value back over your typing. It now only changes a box when the saved setting itself changed (for example by voice), never because of what you are typing. Remember to press Enter or click away from a box, then **Save settings**.
- The menu buttons (Home, Voice, Listening...) now have a visible outline; the page you are on is outlined in bright cyan.

## Record my buttons (0.10.2)
Use this to work out macros together. You do the real button presses on your X52, it writes down every button and the exact timing, and you send me the file.

**How to use it**
1. Double-click **run_record_buttons.bat** (or press **Record my buttons** on the dashboard's Controls page).
2. Type what you are recording, for example `request docking`, and how many seconds (Enter = 20).
3. A countdown beeps. Switch to Elite and do the whole thing as you would for real, pausing where you would wait for the game.
4. Two beeps mean it has finished. The report is saved in the **recordings** folder. **Send me the `.txt` file.**

It presses nothing. It only watches.

**What the report shows**
- Every press and release with the time in seconds, how long each was held, and which of your Elite actions that button is (for example `-> UI_Select`).
- What the game was doing: which screen was open (galaxy map, station services...), switches that changed (docked, landing gear...) and journal events (for example `DockingGranted`), so we can see what you waited for.
- A **suggested macro** already written in the format `config/settings.json` uses, with waits, holds and repeats worked out.
- A **Check** list for anything that needs attention.

**Things to know**
- Starling can only press KEYBOARD keys. If an action is only on a joystick button, the Check list says so: bind a spare keyboard key to that action in Elite's controls and the macro will work.
- Windows only shows the first 32 buttons and one hat per joystick, and no stick movement or sliders. X52 mode-shifted buttons may not show as separate buttons.
- A button shown with a (?) matched your controls file by button number only (the stick is named differently in the file). Check those.
- The screen is only checked four times a second, so a screen that opened at the same moment as a press can be shown just after it.
- The recording folder holds your commander's game events (system names). Look before you share it publicly.
- I could not test this with a real X52 or Windows. If a button you press does not appear, tell me which one.

## Macros built from your recordings (0.10.4 and 0.10.5)
- **Request docking** and **plot the next waypoint** now follow the button presses you recorded on your X52, with your own timings.
- **Plot the next waypoint** (galaxy map): open the map, Up to the search box, Select, paste, Select, wait 4 s for the map to fly there, zoom in a little (hold your zoom-in key for 0.2 s), wait 0.8 s, hold Select 1.2 s to set it as the target, wait 3 s, Back twice. No Enter key and no Down press after the paste.
- **Hands free after a neutron supercharge:** **Plot each waypoint in the galaxy map for me** (Navigation page) is now ON by default. When you get the supercharge she waits **4 seconds**, then runs that macro for the next waypoint, whose name she has already put on the clipboard. She will not start it while jumping, low on fuel, overheating, in danger or being interdicted. Weapons out and the FSD charging do NOT stop it. If she skips one, `logs\starling.log` says why.
- Your waits are slow on purpose. Once it works, shorten them in `config\settings.json` under `macros` (`plot_waypoint`, `request_docking`).
- Your "Open galaxy map" key is a chord (E + W + R held together), which Starling presses as one combination. Because it is a chord that games can miss, if the map does not open, tell me.
- The zoom uses Elite's `CamZoomIn` action (your keyboard Z). Your zoom on the stick is probably a slider, which the recorder cannot see, so I don't know exactly when in the wait you zoomed; I put it just before the held Select. Tell me if it should be earlier or longer.

### Fix in 0.10.7: the macro never ran by itself
Two faults: the hands-free plotting was never connected to the voice commands, and it was switched off by default. Now:
1. After you ask for a route ("plot a neutron route to Home"), she copies the first waypoint and runs the galaxy map macro 3 seconds later.
2. At each neutron star, **4 seconds after the supercharge**, she runs it for the next waypoint.
If your Navigation page already has the toggle saved as off, switch it on and Save settings.

## 0.11.0: biology, thank-yous, learning, Navigation buttons

**Biology scans**
- She now tells you what the species is worth on the FIRST scan (not the third). The analysis at the end only tells you what you are carrying.
- If the species is one of the 10 most valuable she gets excited about finding more. The top 10 is worked out from `config/exobiology_values.json` (and from any real sale prices she has learned).
- On the SECOND scan she describes what it is, in a sentence or more. The descriptions are in `config/bio_info.json` (written in my own words from the Elite wiki, Canonn and community notes; Anemone has no description yet). Edit or add to it freely. Her lines are in `voicepacks/default/bio.json`.
- Species she has no price for are admitted, not invented.

**Docking** no longer presses the final Down.

**Mood** is saved every time it changes (with a backup copy), and she no longer "calms" while the game is closed, so closing and reopening can't wipe it. The old score from before the fix could not be recovered.

**Thank you** After asking for something by voice, say "thank you" (in the same sentence or within 30 seconds). She says "you're welcome" in a different wording each time, and her mood goes up a little. Not saying it costs nothing. Each request can only be thanked once, and the mood engine's normal soft cap stops point farming. Lines: `voicepacks/default/manners.json`.

**Speech learning** She can't retrain the speech recogniser itself (that needs hours of recordings), but she learns how YOU get mis-heard. When a sentence is close to a command and she works it out, she makes a note. After it has meant the same thing twice it becomes one of your phrases and is understood instantly. Saved in `data/voice_learning.json` (delete it to start again). Switch off with `"stt": {"learning": false}` in `settings.json`. Big actions (jump, supercruise) are never learned this way.

**Void Compass overlays** The release notes show no overlay newer than Galaxy Minimap and Postcards, which she already knew. Instead of guessing, she now asks Void Compass for its live list a minute after starting and adds voice commands for any overlay she doesn't know ("show the <name> overlay"). The log says which were added.

**Navigation page buttons** *Plot neutron route to my destination*, a box to type any system and *Plot to this system*, *Plot the next waypoint in the galaxy map* (waits 4 seconds so you can click back into Elite), and *Clear the route*.

**Not tested here:** Windows, Elite, the X52, Spansh and Void Compass (all tested with fakes only). The Navigation page itself can't be shown without a screen; its actions are tested.

## "Launch" from a station (0.27.0)
Say "launch", "auto launch", "launch from the station" or "undock" while docked and she presses UI Select (after 0.3 s) on the station menu. She refuses with "We are not docked, Commander." anywhere else. If your menu needs different presses, put your own steps in `config/settings.json`:

    "macros": { "auto_launch": ["wait 0.3", "UI_Down", "UI_Select"] }

Cargo scoop: "lower / raise / drop / retract the cargo scoop" (and "scoop down / up") already worked.

## 0.28.0: honk fixes, update screen, more jump speech
- **Auto honk now also starts from a separate "arrived" signal**, so it works even if you switched her jump speech off. If the cockpit is in combat mode (hardpoints away) she presses your Cockpit mode key first (needs a keyboard key), honks, then switches back (`autohonk.switch_mode`: false in settings.json stops that).
- **Exploration page > Test the honk now**: click back into Elite and 4 seconds later she honks once and tells you out loud what happened (no keyboard key on your fire button, Elite not in front, hardpoints out...). A joystick-only fire button still cannot be pressed by Starling: add a second, keyboard binding for it in Elite's controls.
- **Updates page > Copy my log to the clipboard**: paste it into the chat when something is not working.
- **Update screen**: Starling.exe now shows "A new Starling is ready" (Update now / Not now / always update automatically) before she loads. This needs the NEWEST Starling.exe: download it once from the GitHub release page and replace the old one (the exe itself cannot update itself). Turn the question back on in the dashboard Updates page ("Ask me before updating").
- **Void Compass check**: no overlay name triggers a ship control and no ship phrase switches an overlay (there is now a test for this). Bare words such as "navigation" or "cargo" still mean the ship; say "navigation overlay" for Void Compass.
- **Jump speech**: about 140 new lines (many plain or dry), fewer pet names and compliments, and a pool of plain dry remarks used in every mood (`Remark_Dry`). Flirty remarks happen less often (switch the Flirty setting off for none).

## 0.29.0: Developer tab, any HOTAS, microphone box, ship model
- **Developer tab** (last in the sidebar): Test her voice, Test the honk, Check my Elite keys, Look for my joystick / HOTAS, Record my buttons, Copy my log, and the "Try a command" box. Nothing there changes how she behaves.
- **Any HOTAS**: sticks, throttles and pedals of any make are found (X52, X56, Warthog, T16000M, VKB, Virpil, Honeycomb...). Elite's controls file names the device ("ThrustMasterWarthogJoystick"); she matches that to the real device. Buttons 1 and 2 of each flight stick count as fire 1 and 2 for the pips (setting `combat_assist.x52_trigger`, now "Joystick trigger counts as fire 1 and 2").
- **Microphone box** at the top of the window: green "LISTENING" while she can hear you (with push-to-talk it lights only while the mic is open), grey "PUSH TO TALK" when it is closed, "MIC OFF" / "MIC STARTING" / "MIC PROBLEM" otherwise.
- **Ship card** shows your own name for the ship and the model next to it ("Pooh bear (Caspian Explorer)"), and the picture follows the model. New ships added: Caspian Explorer, Kestrel Mark 2, Type 11 Prospector, Type 8 Transporter, Lynx Highliner.
- **Home page boxes** wrap their words to the box width, so nothing is cut off.


## 0.30.0: glide, scoopable stars, undiscovered systems, jumps left, own pet names, Caspian x6, Nomad
* **Glide:** when you start gliding to a planet she says its surface temperature (kelvin) and gravity (g). Over 2 g she warns you it is heavy. This needs a scan of that planet (the game scans nearby bodies by itself, or use the FSS); with no scan she just says "Glide engaged".
* **Scoopable star:** when a hyperspace jump starts she says whether the star you are jumping to can be scooped (classes O B A F G K M can; neutron stars, white dwarfs, black holes, brown dwarfs cannot).
* **Undiscovered system:** the first scan after you arrive tells the game whether anyone discovered the system. If nobody did she says so, with funny chatter (50 lines, plus lines for her moods).
* **Jumps left:** after a jump she sometimes (about 3 times in 10) says how many jumps are left, and always says "last jump" for the final one. It uses the route you plotted in the game (or by neutron plotter). Switch off with the Exploration "She comments" switch, or the JumpsLeft entry in config/events.json.
* **Own pet names:** Personality page > "My own pet names". Type names with commas between them. She mixes them in with hers (often when happy, rarely when upset).
* **Caspian x6:** when you fly the Caspian Explorer the neutron plotter uses x6 for you (Navigation page > "Use x6 automatically in the Caspian Explorer").
* **Nomad:** when you recover the Nomad she puts the hardpoints away 2.5 seconds later, if they are out (Exploration page > "Put the hardpoints away when the Nomad docks"). Elite must be the window in front.
* Could not be tested without the game: the real journal values (SurfaceTemperature, SurfaceGravity, WasDiscovered, RemainingJumpsInRoute) and the Nomad recovery. If a callout is missing, use Developer > Copy my log and send it.


## 0.31.0: boost stars, fuel warnings, waypoint count, quiet map macro, game target
* **Neutron stars and white dwarfs:** when a jump starts she says they are for supercharging only (not for fuel).
* **Fuel warnings:** a gentle "we should start looking for fuel" at 50 percent, the game's own low fuel warning at 25 percent (with extra lines, a few teasing Curd Nerd), and panic at 10 percent. Each is said once per tank and comes back after you refuel above 60 percent. Not while docked or landed. The 10 percent one is a safety warning and cannot be switched off.
* **Waypoints left:** the neutron plotter now says "6 waypoints to go" (or "Last waypoint") each time you reach one.
* **Quiet map macro:** while the "plot the next waypoint" macro opens and closes the galaxy map she no longer says "galaxy map opened / closed".
* **Plot to the game's target:** pick a destination in the galaxy map, then say "plot a neutron route" (or "plot neutron course to my target"). She reads the end of your plotted route from the game's NavRoute.json. "Plot a neutron route to my destination" uses the Navigation page box first, then the game's target. "Plot neutron course to Home" uses your Home bookmark.
* Not testable without the game: NavRoute.json contents and the exact moment the game reports the map closing.

## 0.31.1: neutron route as soon as you set a target
Pick a destination in the galaxy map and she plots the neutron route to it by herself (Navigation page > "Plot a neutron route when I set a target in the galaxy map", on by default). She ignores targets her own waypoint macro or a "where to sell" lookup sets, a target that is already part of the route she follows, the system you are in, and the same target twice in a row. Not testable without the game: when exactly the game writes NavRoute.json after you set the target (she waits 1.5 seconds).

## 0.31.2: by voice, to the game's target
Set a target in the galaxy map, then say "plot neutron route", "start the neutron plotter" or "plot neutron". She plots to that target. "My destination" now also means the game's target first (the Navigation page box is only the fallback). The automatic version from 0.31.1 is now OFF by default (Navigation page switch).

## 0.31.3: automatic releases, every mineral in the Mining boxes
* `.github/workflows/release.yml` now runs by itself when `core/version.py` changes on the main branch: it makes the tag and the GitHub Release, builds Starling.exe and the zip. Nobody has to create a release by hand any more (takes about 5 to 10 minutes on GitHub; watch the Actions tab). Starling.exe then offers the update at the next start.
* The ten "Excited about" boxes list every mineral, metal and ice (A to Z). Anything in the list can also be named in speech ("where do I sell the cryolite").

## 0.31.4: neutron plotter and mishearings
From a real log: the microphone heard "neutron plotter" as "neutron platter", "plot neutron course" as "plot neutron cores", "route" as "root", "neutron" as "neutral" or "Neatron". In a sentence about neutrons these are now corrected. The log now says which destination she found in the game (`The destination set in the game's galaxy map: ...`).

## 0.31.5: Set Target as well as Plot Course
The game does two different things. Plot Course writes the whole route to NavRoute.json. Set Target only selects the system (the journal's FSDTarget event). Both now work for "plot neutron route": she uses the selected target if it is not part of an already plotted course, otherwise the end of the plotted course. Arriving at the target clears it. Not testable here: exactly what the game writes for Set Target; the log line "The destination set in the game's galaxy map" shows what she found.

## 0.32.0: emergency protocol (EDAstro) and "clear the route"
When you ask for a neutron route and Spansh does not know the system you are in:
1. She says so and asks EDAstro (edastro.com, free, 100 requests per 15 minutes) for the landmark nearest your galaxy coordinates (the journal gives them). If Spansh doesn't know that landmark either she asks for better rated ones.
2. She plots a course to it in the game with the galaxy map macro (needs "Plot each waypoint in the galaxy map for me" on; otherwise the name goes on your clipboard).
3. When you arrive there she plots the neutron route from the landmark to your real destination, and the normal auto plotter takes over.
You can start it by hand: set a target in the galaxy map and say **"emergency protocol"** (also "I'm lost", "Spansh can't find me", "find me the nearest landmark"). Switch it off on the Navigation page. **"Clear the route"** (also "cancel / reset the route", "clear the course") clears her route and any emergency in progress. It cannot clear the route inside the game itself.
Not testable here (the sandbox cannot reach edastro.com): the exact reply EDAstro sends. She reads the system from its `galMapSearch` field (falling back to `system` or `name`) and only uses it if Spansh knows that exact name. If EDAstro changes, send me the log line starting "edastro".

## 0.33.0: welcome home, map already open, favourite ship, Watcher hush
* **Welcome home:** fill in Home on the Bookmarks page. When you arrive in that system she welcomes you (at most once every 20 minutes).
* **Galaxy map already open:** the "plot the next waypoint" macro (also used by the auto plotter, neutron routes and the emergency protocol) looks at Status.json. If the galaxy map is already open it skips pressing the map key, which would have closed it, and carries on from the search box.
* **More ship comments:** about 30 lines when you swap ships, 15 for the login hello, in every mood (`voicepacks/default/ships.json`).
* **Favourite ship:** every mood gain (good jump, sale, kind word...) is counted for the ship you are flying (`data/favourite_ship.json`). At 20 good points a ship becomes her favourite and she says so; another ship replaces it only by collecting more. She is happier when you fly it, and answers "what's your favourite ship?". Change the threshold in `personality/favourite_ship.py` (THRESHOLD).
* **Void Compass hush:** newer Void Compass has `POST /voice/hush` ("keep the Watcher quiet while my own voice assistant talks"). Whenever she is about to speak, or it is a bad moment for him, she asks for a 12 second hush (at most every 6 seconds). Controls page: "Ask Void Compass to keep the Watcher quiet while she talks". If your Void Compass rejects the call 3 times she stops asking and the log says why. Also added to the client but not yet used: `watcher_answer` (`POST /watcher/answer`). Void Compass's new start/stop voice events are written to the log once so I can learn their format.
* Not testable here: the exact body Void Compass wants for hush (she sends `seconds` and `duration`), the real GuiFocus value while the galaxy map is open (6 in the journal documentation), and the voice start/stop events.

## 0.34.0: new launch and docking macros

Both macros were rebuilt from your button recordings.

- **Request docking**: left panel, Next Tab twice, Select (sends the request), Previous Tab twice, Back.
- **Auto launch** (only while docked): left panel and right panel tab hopping, a tap of the focus button, Down, Select.

Not tested in the game (I can't run Elite). If a pause is too short or long, put your own steps in
`config/settings.json` under `macros.auto_launch` or `macros.request_docking`.

### 0.34.1
Auto launch now presses Select twice at the end (0.8 s apart). Untested in game; edit `macros.auto_launch` in `config/settings.json` if it needs a different pause.

### 0.34.2
Auto launch follows your 13:25 recording: both panels are closed with Back, then Down and Select. Untested in game (the recording shows no Undocked line, so I could not see the launch itself).

### 0.34.3: Select opened chat

Your Elite controls have Enter on both UI Select and Quick Comms Panel, so out in the hangar the macro's Select opened chat. Two ways to fix it:

1. In Elite, Options > Controls, give **UI Select** a second keyboard key (for example Numpad Enter) in its second slot. Starling now picks the key that no other action shares.
2. Or take Enter off **Quick Comms Panel** (Comms section).

The "Key clash" warning in the log tells you which actions share a key.

## 0.34.4: launch talk, "take us out", docking

- **Auto launch talks**: she says a line when she starts ("I have control"), one while the panels are checked ("Checking systems"), and one just before undocking ("All systems green. Taking us out."). The lines are in `voicepacks/default/launch.json` (keys `Launch_Start`, `Launch_Systems`, `Launch_Go`, plus a few per mood). Add your own lines there.
- **New ways to ask** (docked only): "take us out", "number one, take us out", "you have control", "you have the helm", "take her out", "get us out of here", "the ship is yours", "take the helm", "engage launch sequence".
- **Macro speech**: a macro step like `"say Launch_Go"` makes her say a line from that dialogue key. If you write your own `macros.auto_launch` without `say` steps she just confirms as before.
- **Request docking** presses Right again before Select (the step that worked in 0.10.4). Untested in game. If it still fails, edit `macros.request_docking` in `config/settings.json`.

### 0.34.5: key clash list

**Check my Elite keys** (Controls page) and `run_controls_test.bat` now also list every key that one of her commands presses but Elite also gives to another ship action, for example "UI Select (key Enter) is also used by Quick Comms Panel". Change one of each pair in Elite: Options > Controls. If an action has two keyboard keys she already prefers the one nothing else uses. SRV, on-foot and fighter versions of an action are ignored. Joystick buttons are not checked, because she only presses keyboard keys.

## 0.34.6: more Watcher replies

`voicepacks/default/watcher.json` grew from about 100 to about 220 lines. They are written for a Watcher who is gloomy and brilliant, like Marvin the paranoid android: she teases his doom when she is cross, cheers him up when she is happy, and fondly puts up with him when she is close. Infatuated and Upset moods now have their own sets instead of falling back to Neutral. A few Frustrated lines are marked `mature` and only play with strong language switched on. Add your own lines to the same file.

### 0.34.8: only clashes that can really happen

Two actions only get in each other's way when they work in the same view. She now groups every Elite action into one of: ship (flying, targeting, cockpit panels and menus), galaxy map, system scanner (FSS), surface scanner (SAA), camera, SRV, on foot, fighter, multicrew. Key clashes between different groups are ignored, both in "Check my Elite keys" and in the log warnings. The grouping is by action name (`view_of` in `control/binds.py`), so a few odd actions may land in "ship" and be reported when they would not matter. Tell me which and I'll move them.

## 0.34.9: docking, with a self-check

- The docking macro is now your 12:38 recording exactly (left panel, Next Tab, Next Tab, Select, Previous Tab twice, Back). The Right press is gone because Right shares a key with Yaw Right. Every key is held 0.15 s, like the buttons in your recording, instead of her usual 0.06 s tap.
- After every macro the log gets a line like `Macro request_docking trace (...): FocusLeftPanel>gui2, CycleNextPanel>gui2 ...`. The number is the screen the game showed (Status.json GuiFocus): 0 cockpit, 1 right panel, 2 left panel, 6 galaxy map. If the first number after FocusLeftPanel is not 2, the left panel never opened.
- Four seconds after a docking request the log says either `the game answered` (journal DockingRequested/Granted/Denied) or `did NOT answer`.
- New setting `commands.key_hold` (default 0.06 seconds) in `config/settings.json` sets how long every macro key is held. Try 0.12 if keys get missed.

### 0.34.10: docking waits for the panel

Your 17:03 trace showed `FocusLeftPanel>gui0`: the game was still showing the cockpit 0.85 s after she pressed Focus Left Panel, so the first Next Tab presses may have been lost and Select landed on the wrong tab. The docking macro now waits 1.6 s after Focus Left Panel, 0.7 s between the tab presses and 1.6 s before Select. If it still does not work, tell me which tab is highlighted when you open the left panel by hand and which one she ends on.

## 0.35.0: routes to your fleet carrier and the squad carrier

Say any of these (the usual neutron route is plotted, from where you are to the carrier's system):

- "Starling, plot a route to my fleet carrier" / "to my carrier" / "take us to my carrier" / "set a course for my carrier"
- "Starling, plot a route to the squad carrier" / "the squadron carrier"

**Your fleet carrier.** She learns where it is from the journal: `CarrierStats` (its callsign), `CarrierLocation` (when you load the game), `CarrierJump` and docking at it. The journal only tells her about the carrier when you have played with it, so if she says she doesn't know, dock at it once, or type the system in the new **Fleet carrier** box on the Bookmarks page, or say "save this system as my carrier" while you are in its system.

**The squad carrier.** The journal never says where a squadron's carrier is, so she cannot find it by herself. Stand in its system and say "save this system as the squad carrier" (or type it in the **Squad carrier** box). If nothing is saved she says so; if she knows you are in a squadron (`SquadronStartup`) she names it, otherwise she says she can't find a squad.

If you are already in that system she says so instead of plotting. Her lines are in `voicepacks/default/carriers.json`.

Not tested on a real game: the journal field names come from the Elite journal manual and from memory. If "my carrier" is never learned, send me a journal and I will check the field names.

## 0.35.2

The "exit supercruise" voice command from 0.35.1 was removed again, as asked.

## 0.36.0: she reads your messages out loud

Wing, squadron, local, friend, direct, system and crew messages that arrive in the game (the journal's `ReceiveText`) are read out one at a time, but only when nothing else is happening: she is not talking or asking you something, no safety warning in the last 30 seconds, and the ship is not jumping, in danger, overheating, low on fuel or has weapons out. A message that waited more than 3 minutes is dropped, and only the newest 6 are kept. Links are read as "a link".

Two switches on the Personality page: **Read my incoming messages out loud** (on) and **Also read computer-controlled ships and stations** (off: pirates, stations and police talk a lot). Her lines are in `voicepacks/default/messages.json`.

Not tested with the real game: the journal field names (`From`, `Message`, `Channel`, `_Localised`) are from the Elite journal manual.

## 0.37.0: galaxy regions

When a jump (or a carrier jump) takes you into a different galaxy region she says its name ("Entering the Galactic Centre"), and if you have never been in that region before the line says so ("First time in ..."). Nothing is said when you load the game, only on a jump into another region.

- The region is worked out from the system's coordinates (`StarPos` in the journal) with the community region map (42 regions) in `navigation/region_data.py`, by Ben Peddell, MIT licence (`docs/THIRD_PARTY.md`).
- The first time she runs she reads all your old journal files once, in the background, to learn which regions you have already visited. This can take a few seconds to a minute if you have years of journals. Until it finishes she announces the region but does not claim it is new. The result is kept in `data/regions_visited.json`; delete that file to make her scan again.
- Switch it off on the Exploration page: **Announce the galaxy region I enter**.
- Her lines are in `voicepacks/default/regions.json`.

Not tested with the real game: the region map was checked against known systems (Sol is Inner Orion Spur, Sagittarius A* is the Galactic Centre) but not against live jumps. The game shows the region of the boxel corner in some cases, so right at a region edge she may disagree with the galaxy map by one jump.

## 0.38.0: far enough from the last biological sample

After each biological sample she remembers where you stood (Status.json latitude, longitude and the planet's radius) and watches how far you walk. When you are as far as that species needs (config/exobiology_values.json, `colony_distance_m`: for example 150 m for Aleoida, 500 m for Bacterium) she plays two short beeps (Windows) and says so, once per sample. Finishing the third sample cancels it.

Two switches on the Exobiology page: **Tell me when I'm far enough from the last sample** and **Beep as well**. Her lines are in `voicepacks/default/biodistance.json`.

Not tested with the real game: the distance maths is tested, but Status.json only gives your position while you are close to the planet's surface, so if you are in a vehicle that doesn't report it she stays quiet. Tell me if the distances feel off for a species and I will adjust the table.

## 0.39.0: "I want to go merit mining"

Say "Starling, I want to go merit mining" (also "merit mining", "mine for merits"). She searches Spansh (spansh.co.uk, free, no sign-up) for systems that:

1. are **controlled by your pledged Power** (Fortified, Stronghold or Exploited),
2. have a planet with a **Pristine Metallic ring**, and
3. have a **station or outpost** (never a fleet carrier) with a market that wants **2000 tonnes or more** of a metal (Platinum, Osmium, Painite or Palladium).

She says the two nearest matches as **Option A** and **Option B** (planet, system, distance, the station and how much it wants), asks which, then "Would you like me to plot a route for you?" and, on yes, puts the system into the galaxy map with the auto plotter (the same galaxy map macro the "where to sell" answers use). With only one match she goes straight to the route question.

- **Your Power:** she reads it from the journal (the `Powerplay` event when you load the game while pledged). If she doesn't know it, choose it on the Mining page: **Your Power for merit mining**.
- **Switch:** Mining page > **Find merit mining spots**.
- **Metals:** `merit.commodities` in `config/settings.json` (default Platinum, Osmium, Painite, Palladium).
- Her lines are in `voicepacks/default/merit.json`.

Checked live against Spansh's own search while building this (a power's systems, Metallic + Pristine rings, and station markets with demand 2000+), but not with a real game session. Limits: Spansh only says which Power CONTROLS a system, so systems that are merely influenced are not found. Spansh's data is only as fresh as the last player who docked there, so a market may have changed. She needs to be talked to by name (wake word or push-to-talk) like her other answers.

## 0.40.0: "take me to <engineer>"

Say "Starling, take me to Felicity Farseer" (also "take us to", "go to", "navigate to", "fly to", "plot a course to") with any first name, last name, nickname or the full name of one of the 38 engineers (list in `docs/ENGINEERS.md`). Titles are optional ("Dekker", "Colonel Bris Dekker", "the Dweller", "Sarge"). If the microphone mishears a name she takes the closest one.

- **1000 light years or closer:** she puts the engineer's system into the galaxy map with the auto plotter (the galaxy map macro).
- **Farther:** she asks Spansh for a neutron route to the system and plots it like any neutron route.
- **Already there:** she tells you which station.
- **"Where is Felicity Farseer?"** gives the system, the station and the distance.
- The 1000 can be changed on the Navigation page. The engineers are in `config/engineers.json` (add an `aliases` list to an engineer to give a name another spelling).

Not tested with the real game: the galaxy map macro and Spansh's live route. The engineer list comes from EDDI's data (38 engineers); if a new engineer is added by Frontier, add a block to `config/engineers.json`.


## 0.41.0 - On-foot voice control and auto shields

Every on-foot (Humanoid) key from your Elite controls can now be said. Each one needs a KEYBOARD key in Elite's on-foot controls (a second binding is fine).

Things you can say (no "Starling" needed when listening is open, as with the other commands):

| Say | Presses |
|---|---|
| "suit shields" / "raise my suit shields" | Toggle Shields |
| "torch" / "flashlight" | Toggle Flashlight |
| "helmet night vision" / "visor night vision" | Toggle Night Vision (on foot). Plain "night vision" is still the ship's |
| "use a health pack" / "heal me" | Health Pack |
| "use a battery" / "energy cell" | Battery |
| "throw a grenade" | Throw Grenade |
| "next grenade type" / "previous grenade type" | Next / Previous Grenade Type |
| "select frag grenades" / "EMP grenades" / "shield grenades" | the three grenade select keys |
| "primary weapon", "secondary weapon", "utility slot", "next weapon", "other weapon", "holster", "reload", "melee" | weapon keys |
| "energy link", "composition scanner", "suit tool", "tool mode" | the tool keys |
| "interact", "jump over it", "crouch", "sprint", "walk", "aim", "item wheel", "emote wheel", "ping", "mission help", "access panel" | the rest |
| "wave", "dance", "point", "salute", "clap", "shrug", "thumbs up", "sit" | EmoteSlot1 to 8, see below |

EMOTES: Elite does not tell Starling which emote is in which slot. `config/emotes.json` maps a word to a slot number (1-8). The numbers are a FIRST GUESS: open your emote wheel in the game, see which slot is the wave, and edit the number in that file (you can add words too). Restart Starling after editing.

AUTO SHIELDS (Combat page, off by default): when you pull out a weapon, or your health drops while on foot, she presses your Toggle Shields key once. Please read the limits:
* Elite only has a TOGGLE key and does not say whether the shields are up. If they were already up, her press turns them off; say "suit shields" to flip them back.
* She counts her own presses: after she raises them she waits until you holster and draw again, or leave the suit.
* "Weapon in hand" comes from the Status.json field SelectedWeapon. Its exact wording could not be checked here; fists, tools and scanners are ignored.
* Several keys in a typical bindings file are shared between actions (for example W is Forward and Battery, E is Interact and Frag Grenade). The key Starling presses may therefore do something else too. Give the on-foot actions spare keys if that bites.

NOT TESTED against the real game (only the logic): any key press, the emote slot numbers, the SelectedWeapon wording.


## 0.41.1 - On foot page, and updates without asking
* The dashboard has an **On foot** page. The auto-shields switch lives there now.
* Updates: the "Update available - Update now / Not now" screen used to be on by default, so Starling.exe waited for a click. It is now OFF by default, and the first time this version runs it is switched off in your saved settings once. Switch "Ask me before updating" on (Updates page) if you want the question back. The update is still installed only when you close Starling and open Starling.exe again.


## 0.42.0 - Five levels in every mood, a bigger score range, more personality

* **Score range x5.** The hidden score now goes from -500 to +500 (it was -100 to +100). Every action still gives the same points, so she takes about five times longer to reach the top (about 15 days of play instead of 3). The hourly cap, calming and soft cap work as before. Wanted/notoriety and worn paint pull her down towards floors that are five times lower, at twice the speed.
* **5 levels in every mood.** Infatuated, Close, Friendly, Neutral, Sarcastic, Frustrated and Upset are each split into 5 steps. Level 1 is where she arrives in the mood, level 5 is just before the next mood up, so going up a step always makes her a bit friendlier and going down a bit colder. The Home page shows it ("Friendly 3/5 (+120)").
  Ranges (score): Upset below -300, Frustrated -300 to -175, Sarcastic -175 to -50, Neutral -50 to +50, Friendly 50 to 150, Close 150 to 300, Infatuated 300 to 500.
* **Your saved mood is converted once.** She keeps her mood but lands near the start of it (a maxed-out Infatuated becomes Infatuated level 2, so there is room to climb; a bad mood starts near its neutral end).
* **What changes in her speech.** After lines she adds a short aside written for her mood AND level (Tone_<Mood>_L1 to L5 in voicepacks/default/tone.json, 245 lines). Her comments are a little more frequent the warmer she is, and the bad moods are snippiest at level 1. Neutral now makes comments about 1.6 times as often and has 30 new dry lines (neutral.json), so she keeps her personality when calm.
* **Fixed mood** (Personality page) now also has a **Fixed mood level**.
* I added to her lines rather than rewriting the thousands she already had. Tell me which mood or area sounds flat and I will rewrite those lines.
* NOT tested: how the new lines sound spoken, and how it feels over days of real play.


## 0.42.1 - A clearer key check
"Check my Elite keys" (Developer page) now lists each command she cannot press with its reason, shows when Elite last saved the controls file, and copies the whole report to the log (Copy my log). Elite only writes new keys to that file when you press APPLY in the controls screen.


## 0.42.2 - The Apps key
Your HCS controls file puts many on-foot actions on RightAlt + Apps + a key (for example Health Pack on RightAlt + Apps + Q). Starling did not know the Apps (menu) key, so it called all of those commands "unknown key" and would not press them. She knows it now (scancode 5D). This also fixes the emotes, grenade types, battery, weapon switching and aim commands.


## 0.42.3 - On-foot keys from the on-foot preset
Elite lets the ship and the on-foot controls use different presets (the on-foot page of your controls says PRESETS: MCUSTOM, while the ship uses HCS Custom). Starling only read the ship's file, so she pressed keys from the wrong preset ("salute" pressed a chord that does nothing in your on-foot controls). Now she also reads the other presets named in StartPreset.start, takes the one with the most on-foot keys set, and uses it for every on-foot action. "Check my Elite keys" says which file the on-foot keys came from.

Emote words now follow the game's own list, which is also the slot order: point 1, wave 2, agree 3 (also "thumbs up"), disagree 4, go 5, stop 6, applaud 7 (also "clap"), salute 8. Change the numbers in config/emotes.json if your wheel differs. The old guesses (dance, shrug, sit) were removed because the game has no such emote in that list.
NOT tested against your real files: which preset line is the on-foot one is a guess based on "the other preset with the most on-foot keys".


## 0.42.4 - Finding the on-foot controls file
In 0.42.3 she only looked at the presets named in StartPreset.start, and your log showed it did not find your on-foot preset (salute still pressed the HCS key Right Alt + Apps + S). Now the order is: the preset name you type in **On foot > My on-foot controls preset** (for example MCUSTOM, as your on-foot controls page says; restart Starling after changing it), then the other presets named in StartPreset.start, then any other .binds file in the Elite controls folder (newest first). A file needs at least 10 on-foot keys set to count. "Check my Elite keys" now says which file the on-foot keys come from, what StartPreset.start says, and lists the controls files with their saved times, so we can see what she sees.


## 0.43.0 - The Keybinds page
Elite lets each group of controls use its own preset (the top of each controls page in the game says PRESETS: ...). There is now a **Keybinds** page right under Home with a box for each:
Ship, On foot, SRV, Ship-launched fighter, Multicrew. Type the preset's name exactly as the game shows it (for example `MCUSTOM`), save, and restart Starling. An empty box means "work it out": the ship uses the preset Elite starts with, the on-foot keys are searched for (see 0.42.4), and SRV, fighter and multicrew use the ship's file. Your on-foot box still uses the same setting as before (it already holds MCUSTOM).
Developer > Check my Elite keys shows which groups are read from which file.
NOT tested with real SRV, fighter or multicrew presets.


## 0.43.1 - Preset drop-downs
The boxes on the Keybinds page are now drop-down menus. Each lists "Automatic" plus every preset she finds in Elite's controls folder (the names of the .binds files without the version number, for example HCS Custom and MCUSTOM). A name you chose earlier is kept even if its file is missing. Restart Starling after changing one.

## 0.44.1 - Check my Elite keys on the Keybinds page (list only)

**Keybinds > Check my Elite keys** (moved from the Developer page) lists the missing keybinds, the files she read and any key clashes. She never writes to your Elite controls files and never changes a key: you set the missing ones yourself in Elite (Options > Controls), then press Apply and check again. (A fill-in helper was built in 0.44.0 and removed again at your request.)

## 0.44.2 - Shields come down when you holster

With **On foot > raise my suit shields** switched on: weapon drawn = shields up, weapon holstered = shields down (she presses your Toggle Shields key again). She only lowers shields SHE raised; if you raised them yourself she leaves them. Drawing again straight away raises them again (no waiting). Shields raised by damage while your weapon is away stay up until you draw and holster. Not tested in the live game.

## 0.45.0 - On-foot care

New switches on **On foot** (the medpack and energy cell ones are OFF until you switch them on):
- **Shields in a fight.** The game has no "I am in a combat zone" flag. She treats you as in a fight for 2 minutes after a combat bond (those only happen in conflict zones), a bounty, or taking damage on foot. In a fight she raises the shields if they are down and does NOT lower them when you holster. When the fight is over and your weapon is away, they go down. She cannot raise them before the first sign of a fight.
- **Medical pack at 20% health or lower.** Health is in Status.json, so this one is exact. Waits 6 seconds between uses.
- **Energy cell when your shields are gone.** The game does not share the shield level (not in any file). Damage hits shields first, so the first loss of health is her sign. Waits 25 seconds between uses.
- Both only press when your backpack still has one (read from Backpack.json); if it is empty she says so (at most every 30 seconds) and presses nothing.
- **Last grenade.** When a grenade type in Backpack.json goes from 1 to 0 while you hold a weapon she says "That was your last frag grenade". Lines: `voicepacks/default/onfoot.json`.

**Low ammo is NOT possible.** The game does not put your ammo in Status.json, the journal or any file. I will not guess.

Not tested in the live game: the exact item names in Backpack.json (the log line "Backpack: ..." shows what she reads, please send it if grenades or packs are not noticed), whether the game writes Backpack.json straight away when you throw, and the key presses.

## 0.45.1 - Energy cell uses suit energy

The energy cell now follows your SUIT ENERGY (20% or lower), not shields. The game's manual lists no suit energy in Status.json (only Oxygen, Health, Temperature, SelectedWeapon, Gravity), so she looks for a field called SuitEnergy, Energy, SuitPower, Power or Battery in case your game has one, and the first time you are on foot she writes ALL the fields she sees to the log ("Status.json on foot has these fields: ..."). If one is found she uses it. If not, she falls back to the first loss of health as the sign that the shields are gone, and the log says "Suit energy field: not found". Please send me that log line if the cell does not use itself at the right time, and I will wire up the real field name.

## 0.45.2 - Request docking, your sequence

Focus Left Panel, wait for it to open, Previous Panel Tab x3, Next Panel Tab x2 (Contacts), UI Up x5, UI Right (opens the station menu), UI Select (Request Docking), UI Left, Previous Panel Tab x2, Focus Left Panel (closes it). Every press is held 0.15 s with a pause after it. Your list had "Previous Panel Tab x2" twice (steps 7 and 8); I did it ONCE (x2). If the tabs end in the wrong place, tell me and I will make it four.

Needs keyboard keys for UI Up, UI Right, UI Select, UI Left and both panel tabs. UI Right/Left often share a key with Yaw Right/Left: use Check my Elite keys, and give one a second key if it is listed as a clash. The log line "Macro request_docking trace" shows which screen the game was on after each wait, send it if it fails.

## 0.45.3 - Request docking, from your recording

Replaces the 0.45.2 written sequence. Your recording: Focus Left Panel, Next Tab x2, hold Up for 1.4 s, Right, Select (the game answered DockingGranted 0.2 s later), Left, Previous Tab x2, Back. She uses your pacing, with 0.15 s presses and 1.6 s for the panel to open (your recording has it open 0.6 s after the key, but earlier logs showed short waits failing). Change any step under `macros.request_docking` in config/settings.json. If it fails, send the log line "Macro request_docking trace".

## 0.45.4 - Request docking: the panel closes after UI Up

Your 15:13 and 15:28 logs: the left panel opened, Next Tab x2 worked (screen 2), then the screen went to 0 (no screen) right after UI Up, so Right, Select and Left went to the cockpit and the game never heard a docking request. Your UI Up key is W, which is also Forward Thrust (UI Right is D, also Yaw Right). My guess, not proven: a key that is also a flight control makes Elite drop the panel focus.

What 0.45.4 does: after Up, Right and Left she waits 1.2 s, looks at Status.json, and if NO screen is open she presses Focus Left Panel again (new macro step `ensure FocusLeftPanel 2`). Up is one short tap now (the 1.4 s hold closed it at once). Look for "reopened>gui2" in the "Macro request_docking trace" log line.

If it still fails, the clean fix is in Elite: give UI Up, UI Right and UI Left a keyboard key that is not also a flight key (for example the arrow keys on the first slot), then Check my Elite keys should list no clash for them. I have not changed any of your keys.

A quick test that tells us if I am right: with Elite open, press your Focus Left Panel key, Next Tab twice, then W once by hand. If the panel closes, it is the shared key.

## 0.46.0 - Only direct messages

Dashboard > Personality > **Which messages she reads**: *Direct messages only* (the new default), *Direct, friends, wing and squadron*, or *Everything, including local and system chat*. Computer-controlled ships keep their own switch (off). It applies to everyone, so your existing setting changes to direct only after this update. Elite's journal calls a direct message the "player" channel; if one of yours is not read, send me the log line and I will check the channel name.

## 0.47.0 - Mood swings, and more ways to lose points

**Mood swings** (`swings` in config/mood_rules.json): a big event puts her in another mood for a few minutes WITHOUT changing her score. When the time is up she says a forgiving line (or "back to business" after good news) and returns to the mood she really was in. The swing is saved, so closing Starling does not cancel it. The "Reset her mood" button clears it.
- You died: Upset, 5 minutes ("I forgive you").
- You blew yourself up: Frustrated, 3 minutes. Killing civilians: Frustrated, 5. Canopy broken: Frustrated, 2.
- Failed mission: Sarcastic, 3. A sale that lost 200,000+ credits: Sarcastic, 3.
- Good news: a bounty of 2,000,000+: Infatuated, 3 minutes. Selling 10,000,000+ of exploration or biology data: Close, 5 minutes.
A worse swing is never replaced by a milder one; it just lasts longer.

**New ways to lose points** (these DO change the score):
- Dying: the penalty is now only -1 (the sulk is the main punishment, and she is forgiving), but losing unsold data is a second hit: she counts scans, system mapping, codex entries and biology samples since your last sale (a rough count, kept only while Starling is open). Dying with 8+ "units" costs 2, 25+ costs 4, 60+ costs 6.
- A rebuy over 1,000,000: -1, over 10,000,000: -2, over 50,000,000: -3.
- Selling at a loss (she works it out from what you paid): 10,000+ lost: -1, 200,000+: -2, 1,000,000+: -3.
- Dumping cargo -1, being interdicted -1, losing your fighter -1, canopy broken -2, nearly out of fuel -2.

Edit any number in config/mood_rules.json (rules and swings). Not tested in the live game: the real journal fields (AvgPricePaid on a sale, Cost on a rebuy). Also, the lines for medpack, energy cell and last grenade from 0.45 were never loaded by mistake, so she could not say them; fixed now.

## 0.47.1 - Still upset at login

If you load into the game while a mood swing is still running (for example you died 3 minutes ago and restarted), the login greeting says so instead of the usual "how she feels" line: "I'm still upset with you for dying, Commander." Each swing in config/mood_rules.json has a `still` line (Still_Died, Still_General, Still_Good in voicepacks/default/swings.json). A swing keeps counting down while Starling is closed, so after the full 5 minutes the greeting is back to normal.

## 0.48.0 - Show off

Say **"show off"**, "show chat what you can do", "show us your skills" or "impress chat". From the cockpit only (not on foot, in the SRV or a fighter, and not while in danger, being interdicted or jumping) she:
1. says she has the controls, opens the **galaxy map** and talks about routes and engineers, then closes it;
2. opens the **left panel**, flicks through two tabs while she talks, goes back and closes it;
3. does the same with the **right panel**;
4. talks about voice control, her fight and on-foot care, what is NEW, and a closing line.
She waits until each sentence is finished before changing screen. It only opens and closes screens: no key that moves the ship. Each close key (Back) is pressed only if that screen is really open. To stop it, switch off her voice or press the screens closed yourself; she cannot be interrupted halfway.

"What can you do" is still a spoken answer only; it now also mentions "show off".

**Keeping it up to date:** the part about new features is `ShowOff_New` in `voicepacks/default/showoff.json`. When we add something worth showing, those lines are updated (this is part of every release that adds a big feature). The steps are `macros.show_off` (defaults in control/catalog.py): you can add screens, tabs or `talk` steps.

New macro steps: `talk ShowOff_Map` (speak and wait until finished) and `leave UI_Back 2` (press only if screen 2/1/6 is open). Not tested in the live game: the timing of the panels and the galaxy map closing with Back.

## 0.48.1 - Show off: faster and quieter

Your three runs felt slow with long pauses. Causes I could find, all fixed:
- She announced each screen ("opening the galaxy map", "closing it", the panels). These are muted for the whole show-off now (and for a few seconds after).
- She waited for each screen to open BEFORE talking, then waited again. Now she starts the sentence at the same moment as the key press, and flicks the tabs while she is still speaking; the only waits are for her to finish (`finish` step) before she closes a screen.
- Her usual random extras ("by the way..." remarks) were added to these lines, which makes the voice build a new sentence on the spot (slow start). The show-off lines are now spoken exactly as written, so the prepared voice can play them at once.
Macro steps changed: `talk Key` now queues a plain line and carries on; `finish` waits until she has said everything queued. If you still hear long gaps, send me the log: "Slow start: ... (made on the spot)" lines tell us which sentence was not prepared. Run "prepare her voice" once after this update so the new lines are ready.

## 0.48.2: "the first one" / "the second one" instead of A / B
Stream feedback: the microphone and the voice mishear "A", "B" and "Option A". Everything she SAYS now uses "the first one" and "the second one" (where to sell, where to buy, merit mining routes). She understands: "the first one", "the 1st one please", "first", "number one", "the second one please", "the 2nd one", "second", "number two", plus the old "A"/"B". "Either" picks the first (the better price); "neither" or "no thanks" cancels.
Run "prepare her voice" once after this update so the reworded lines are ready.

## 0.48.6: High Grade Emissions callout
When the full spectrum scanner (FSS) finds a High Grade Emissions signal source she says so, once per system, instead of the plain "signal detected". It follows the Exploration "She comments on exploration" switch.
Honest limit: the signal name was written from the journal manual. Every USS signal she sees in the FSS is written to the log ("FSS signal: ..."); if she never calls one out, send me those log lines and I will fix the name she looks for.

## 0.48.7: which High Grade Emissions materials a system is likely to give
On arrival she looks at the faction that controls the system (allegiance and state) and, when it matches the table, says what to expect. The table lives in journal/hge_states.py:
- Independent or Alliance, Boom or Expansion: Proto Heat Radiators, Proto Light Alloys, Proto Radiolic Alloys
- Empire, no state / Election / Boom / Expansion / Investment: Imperial Shielding
- Federation, no state / Election: Core Dynamics Composites, Proprietary Composites
- War or Civil War (any allegiance): Military Grade Alloys, Military Supercapacitors
- Civil Unrest: Improvised Components, Military Grade Alloys. Outbreak: Pharmaceutical Isolators
War, unrest and outbreak win over the allegiance rows. Switch: Exploration page "Tell me which High Grade Emissions materials a system is likely to give".
Honest limits: the table is community knowledge (several guides agree on most rows but not all; "Expansion" is included because you asked) and only improves the odds, it never guarantees the material. Only populated systems have a controlling faction, so empty systems get no hint.

## 0.49.0: Guardian blueprints
Say any of these (the word "blueprint" and "guardian" must be in it):
- "plot me a route to the guardian weapon blueprint" / "...module blueprints" / "...vessel blueprint" (or "fighter")
- "how do I get the guardian module blueprints" (also weapon, vessel, fighter): she talks you through the whole thing, one step at a time
- "where is the guardian weapon blueprint"; add "alternative" to go to the other site
Sites (config/guardian.json, edit it if you find a closer one): module = Synuefe NL-N C23-4 planet B 3 (other: HD 63154); weapon = Synuefe EU-Q C21-10 planet A 3 (other: Synuefe GV-T b50-4); vessel and fighter = beacon Synuefe KU-F B44-4, then the structure Synuefe EU-Q C21-15 planet A 1 (other: NGC 2451A Sector LX-D2-25, then NGC 2451A Sector VJ-RC4-225).
Distance rule is the same as for the engineers: 1000 light years or less (setting "Engineer farther than this many light years") uses the galaxy map plotter, farther uses a Spansh neutron route.
Vessel blueprint: she sends you to the beacon first. About 6 seconds after an Ancient Key lands in your cargo she says where to take it and plots the structure (switch on the Navigation page). Ask for the vessel blueprint again while you hold a key and she goes straight to the structure.
Honest limits: not tested in the game. The key is recognised by the journal's cargo name "ancientkey"; if she never reacts, send me the log line "Collected ..." after you scoop it. The distance needs the system's coordinates from Spansh; if Spansh does not give them she asks for a neutron route (it always works, just slower for short trips). The guides were put together from community walkthroughs (Anti-Xeno Initiative wiki, the Frontier forum Vessel and Weapon walkthroughs, the Canonn module guide) and your notes.

## 0.49.1: Thargoid Titans
Say "plot me a route to the nearest titan", "take me to Titan Thor" (or Cocijo, Hadad, Indra, Leigong, Oya, Raijin, Taranis), "where is Titan Oya", or "what happened to Cocijo".
- Up to 1000 light years she uses the galaxy map, farther a Spansh neutron route (same setting as the engineers).
- On the way, each jump she tells the next piece of the Thargoid war (the first war, the Proteus Wave, the Maelstroms and Titans, the eight hearts, the thermal core, the meltdown, the last battle at Sol), with a piece about that Titan in third place. At most one piece every 40 seconds.
- On the jump into the Titan's system she says when it was destroyed and which Titan it was to fall.
- Switch: Navigation page "Titan routes: tell the Thargoid war story on the way".
The Titans are in config/titans.json. All eight were destroyed in 3310: Taranis 2 March, Leigong 17 March, Oya April, Hadad 26 May, Indra 9 July, Thor August, Raijin 24 October, Cocijo 18 December (over Earth, after it moved from Col 285 Sector BA-P c6-18 to Sol).
Honest limits: dates come from the Canonn memorial and the Elite wiki, which disagree by a day or a month for Oya and Thor, so those two are given as a month only. "Nearest" needs Spansh to give the systems' coordinates; if it does not, she asks you to name a Titan. The Titans are gone, so you are visiting the places where they were.

## 0.49.2: how full are your material stores?
After you pick up materials she says things like "you are 82 percent full on iron". Storage limits are 300 / 250 / 200 / 150 / 100 for grades 1 to 5 (raw materials stop at grade 4); every material's grade is in config/materials.json.
So she does not nag:
- She waits 4 seconds after the last pickup and treats everything you just collected as one batch, then says ONE line: the fullest material, the fullest two, or "several materials are filling up, the fullest is ...".
- A material is only mentioned at 25 percent full or more (Exploration page box, 0 = all), and again only when it has grown by 10 more points. The same material at most every 2 minutes.
- At least 25 seconds between lines, and at most 5 lines in any 10 minutes.
- Hitting 100 percent is always said ("Iron is full"), once per material every 5 minutes.
Switch: Exploration page "Tell me how full a material store is".
Honest limits: she keeps the count from the game's "Materials" line at start-up plus every pickup, discard, synthesis, engineer upgrade, trade, technology broker and research hand-in. If she starts in the middle of a session the numbers may be a little off until the game writes the next "Materials" line (when you log in). The limits per grade are community knowledge (confirmed for grades 1, 2 and 5 in a Frontier forum post).

## 0.50.0: Notable Stellar Phenomena (NSP)
NSPs are the clouds at Lagrange points (and in rings) that hold molluscs, pods and trees, crystals and mineral spheres. She knows 28 kinds (config/nsp.json: 1 Lagrange cloud, 1 storm cloud, 6 mineral kinds, 11 molluscs, 9 pods and trees).
- Scan one with the composition scanner: the game writes a codex entry and she says what it is, with a small fact. If the entry is NEW to your codex she is delighted (+3 mood, own mood category); if you have seen it before she is pleased (+1). She comments on how much she loves the colours. The same already-seen kind is mentioned once per session so a cloud full of molluscs does not become a lecture.
- When the system scanner (FSS) finds an NSP signal she tells you, once per system.
- Switch: the Exploration "She comments on exploration" box covers all of it.
Honest limits: she can only say "new" when the codex entry says so (IsNewEntry). The game does not say whether anyone else has found it, so "new" means new to YOUR codex. The FSS signal name for an NSP is not in any source I could open ("$Fixed_Event_Life_Cloud;" is my best knowledge); every "$Fixed_Event..." signal is written to the log as "FSS signal: ...", so if she never announces one, send me those lines. Honking alone does not list the signals, only opening the FSS does. The facts for the plainly shaped molluscs and pods are mostly the meaning of the name: nobody has documented more than that online.

## 0.51.0: exobiology guesses (what lives there, and what it is worth)
- After the system scanner (FSS) finds biological signals on a planet she compares the planet with config/bio_rules.json (116 species) and says things like "two biological signals on A 3, I'd guess Stratum or Tussock, around 4 million credits". The number of signals is the number of different genera, so with two signals she prices two genera.
- If a top ten species fits the planet she says "you might find Stratum Tectonicas on A 3, it might be worth a scan" (at most 3 times in a system, each species once).
- After the surface scan (SAASignalsFound) she says what the genera really are and whether she was right. When you scan a creature (ScanOrganic) the real species is remembered for that planet.
- She forgets all of it when you jump to another system (so it never grows), and speaks at most 5 guesses per system.
- Codex: she remembers which species you already have (data/bio_codex.json, from codex entries and finished samples). The first time she starts she reads your old journal files once, in the background, to learn what you already have. This is what the overlay (next release) uses for the white flags.
- Switches on the Exobiology page: "Guess what lives on a planet" and "Say when a top ten species might be there". The Exobiology "She comments" box covers it too.
- The values come from config/exobiology_values.json, and the real price replaces the estimate after you sell (as before). Prices I added for the Brain Trees, Anemones, Tubers, Amphora, Bark Mounds and Crystalline Shards are community figures from memory and may be a little out until you sell one.
Credit: where each species can live comes from the EDEXO project (github.com/bahuckel/EDEXO), data licensed CC BY-NC-SA 3.0. config/bio_rules.json is a reduced copy and is shared under the same licence: for non-commercial use, with credit. (Starling itself has no licence file yet; if you ever sell it, this file must be removed.)
Honest limits: the rules are community knowledge, not game data, so she will sometimes be wrong; that is why she corrects herself after the surface scan. She ignores a few clues (the star a planet orbits is only roughly checked, some "must be near a nebula or the galactic core" rules, and the Fumerola geological-feature type). The codex flag is for the species, not the colour variant. Not testable here: how it sounds, and the real FSS and surface scan journal lines (the field names were checked against the game's journal manual and EDEXO, not a live game).

## 0.52.0: the biology overlay
A small box on top of the game, bottom left, a quarter of the way up. See-through with an orange border and orange writing (a dark background is a setting). It ignores the mouse, so you can click through it.
- One line per planet in the system that has life: a little planet picture (craters for rocky, bands for metal, glints for ice), the planet name, how many biological signals, a white flag for each signal that could be something NEW for your codex, and the value on the right.
- A value with "~" is her guess from the system scanner. After you scan the creatures (or the surface scan names the genera) the "~" goes. The flags count down as you add species to your codex.
- It disappears when you jump out of the system (she forgets the planets too, so no memory is used), or when you say "hide the bio overlay" (also "close/remove/clear/turn off the biology box/list/panel"). "Show the bio overlay" brings it back; it is shown again in the next system.
- Exobiology page: switch on/off, distance from the left, height above the bottom (both in percent of the screen, so any resolution works), size, dark background, and a button "Show a test biology list for 10 seconds" (shows three made-up planets so you can place it).
- More than 8 planets: it shows 8 and says "and N more".
Honest limits: I could not run this on a real screen (the machine I build on has no screen library). The layout, the voice command and the drawing code were tested against a stand-in, but how it LOOKS (spacing, fonts, text edges on the see-through colour) needs your eyes; use the test button and tell me what to move. Elite must be Borderless or Windowed; a true fullscreen game hides every overlay. It uses your main monitor. A flag means "at least one species there could be new to you", it does not know which signal is which until you scan them. The codex list only knows species from your journals and from now on; very old entries from before your journal files are missing, so some flags may show for species you do own.

## 0.53.0: she learns from her wrong guesses, and a licence file
- Every time a surface scan tells her which genera are REALLY on a planet she compares that with her guess and remembers it (data/bio_learned.json, each planet counted once, a few kilobytes):
  - How often each genus was a candidate and how often it was really there. Genera that keep turning up are named first and count more in the value guess; genera that keep not being there count less.
  - What kind of planet each genus was really found on (planet class, atmosphere, temperature range, gravity, volcanic or not). If the community rules missed a genus but she has seen it on a planet like this before, it now counts as a candidate.
- So the more planets you surface scan, the closer her guesses get. It only learns from planets whose own scan she saw. Delete data/bio_learned.json to make her forget.
- Honest limits: it learns from your own scans only, a single odd planet can widen a genus' envelope (a lot of scans smooths that out), and "wrong" only means the genera differed, the species is not checked.
- LICENSE: Starling is free to use, copy and change for personal, non-commercial use (including streaming), not to be sold; the file also lists the third-party credits (EDEXO data, CC BY-NC-SA 3.0, in config/bio_rules.json, and Frontier's game). I am not a lawyer; if the licence matters to you, have the text checked, or tell me which licence you want instead (MIT, GPL, PolyForm Noncommercial...).

## 0.54.0: learn from all my old journals
Memory page, button "Learn from all my old journals". She reads every Journal*.log in your Elite journal folder, one after another, in the background (you can keep playing and streaming; she pauses between files and reads line by line, so memory use stays tiny). The note at the bottom of the window shows "Reading journals: 12 of 340" and, when done, she says she has finished.
What she learns:
- Which biological species are in your codex (the white flags on the overlay) and which you have finished sampling.
- The real prices from every biological data sale you ever made (later sales win), so value guesses are exact for those species.
- Every surface scan you ever did: which genera were really on which kind of planet, so her exobiology guesses improve (same learning as 0.53.0).
Nothing is spoken while she reads and nothing leaves your computer. Run it again any time: each planet is counted once, so it only adds what is new. A short summary is saved in data/history_scan.json.
Honest limits: it only reads the journal files that still exist in the folder (Elite keeps old ones unless you delete them). A very big history can take several minutes. It does not touch the hours-together or milestone memories (those start from when she first ran); say if you want her to rebuild those from the journals too, or to learn other things (favourite ships, systems visited, first discoveries).

## 0.55.0: systems you own, and a bigger journal button
- Colonies: when the journal says you claimed a system with a colonisation ship (ColonisationSystemClaim) she adds it to the list of systems you own (data/owned_systems.json) and to her memory ("you claimed X as your own system"). If you give one up (ColonisationSystemClaimRelease) it is removed. When you arrive in one of your systems, by jump or when you log in there, she welcomes you home in her current mood (at most once every 2 minutes). The button also finds claims in your old journals.
- "Learn from all my old journals" (Memory page) now also rebuilds her memory from the journals: hours together, jumps, missions completed, times destroyed (each only ever goes up, so running it twice or after playing with her never counts anything twice), your longest jump, biggest biology sale and biggest exploration sale, deaths, big missions (5 million or more) and the first time you sampled each species. The summary line shows hours, jumps, missions, deaths and how many systems you own.
Honest limits: the exact journal line for a claim comes from the EDEXO project's reading of the game, I have never seen one in a real journal, so tell me if it does not work (the claim is also written to the log as an unknown event if the name differs). Hours are the time between the first and last line of each journal file, so a game left running overnight counts. Her "favourite ship" is built from her moods, not from journals, so it cannot be rebuilt.

## 0.56.0: route to the nearest DSSA carrier
Say "plot me a route to the nearest DSSA", "take me to the closest DSSA carrier in the Norma Expanse" or "go to a DSSA in the Void". Any of the 42 galaxy regions works, so it is a way to get to a far region by hopping to a carrier that is already there.
- She loads the list of DSSA (Deep Space Support Array) carriers from EDAstro (edastro.com/mapcharts/files/DSSAdeployments.csv; if that fails the big EDAstro points of interest file), keeps it in data/dssa_cache.json and refreshes it when it is over 12 hours old. If the internet is down she uses the old copy.
- She picks the carrier nearest to where you are (inside the region if you named one) and uses the same rule as the engineers and Guardian sites: up to 1500 light years she uses the galaxy map plotter, farther she asks Spansh for a neutron route (the auto plotter then follows it). The 1500 is its own setting, Navigation page "DSSA carrier farther than this many light years" (engineers stay at 1000).
- If there is no carrier in that region she says so; an unknown region name is also said out loud. "Dissa" and "D S S A" are understood too.
Honest limits: I could NOT open EDAstro's file from here, so the column names are guessed. She finds the columns by their names (system, name, coordinates, status) and skips decommissioned carriers, but if the real file is laid out differently she will say she can't get the list; send me the first lines of the file and I will fix it. Carriers jump, so the list can be a day behind. If the file has no coordinates she asks Spansh for each carrier's system (slow the first time only, then cached). Region names come from the same map as the region announcer.

## 0.57.0: fixes found by studying real journals
I studied a large set of real journals (only to fix the code; nothing from them is stored in Starling or sent anywhere).
- Exobiology guess was too early (important fix): the game writes the biological signals of a planet BEFORE the planet's detailed scan, so she used to guess with no planet data and say she could not work it out. She now waits for the detailed scan (the one you get by flying near the planet or after the FSS) and then guesses. Rules were checked against over a thousand surface-scanned planets: the real species was in her candidate list about 97% of the time. A few conditions were widened and two prices fixed (Tussock Pennatis, Tussock Ventusa).
- Green gas giants: the game has no "green gas giant" planet class, so the old guess (any gas giant with life) was wrong. The only real sign is the codex entry "Green gas giant" (Sudarsky class I and II). She now reacts to that codex entry, with a special line if it is a new discovery. Gas giants with life and rare giants (water giant, helium rich, class V) get their own lines and count as worth a look.
- The "hours together" from the journal button now uses the game's own total play time (Statistics event) when it is in the journals, instead of the time between first and last line.
Honest limits: I cannot play the game here, so the real in-game behaviour is tested only against journal lines, not live. A green gas giant that was scanned but not logged in your codex cannot be told apart from other giants, because the journal does not say.

## 0.58.0: codex progress, the one-of-a-kind species, milestones, first discoveries
- Codex progress (switch: Exobiology page, "Say how far my codex has got"): after you finish a species you had never logged she says how many species are in her codex, and which kinds (genera) you have never sampled once only three or fewer are left.
- Radicoida Unica: it has only ever been found in a single system, so she never guesses it, never lets it teach her wrong habits about other planets, and counts it in the codex. When you take the first sample she says it is the one-of-a-kind species and to be careful. Its price is 46,662,504 and I guessed its sample distance as 100 metres (I could not verify it) (a real sale from the journals, later sales correct it).
- Milestones: the game writes a Statistics line each time you load in. She watches it for round numbers: every 500 hours played, 5,000 hyperspace jumps, 100 first footfalls, 10 biological species. Each is said once (data/game_milestones.json). The first time she ever sees your statistics she only writes the numbers down, so a veteran does not hear "3,500 hours" on day one; a milestone you pass while playing is said the next time you load in (the game only writes the statistics then).
- First discoveries: when nobody has scanned an Earth-like world, water world, ammonia world or rare giant before, she says it is a first discovery. The game's "was discovered" flag decides.
Honest limits: tested against real journal lines only, not live in the game. The milestone steps (500, 5,000, 100, 10) are my choice; tell me if you want different ones.

## 0.59.0: the overlay follows the planet you map, first-discovery lines toned down
- Planet view: when you finish a detailed surface scan (the probes) on a planet with life, the overlay changes to just that planet: its name and one line per life form, a white flag for each that would be new to your codex, and the value. Before you sample a form it shows the genus (for example "Stratum") with an average value marked ~; once you take the first sample it shows the exact species and its price.
- Finished forms: when you finish all three samples of a life form, a line is drawn through it (and its flag goes), so you can see what is done.
- First footfall: if nobody had landed on the planet before (the scan says so), values are times five, in this view, in the list and in her spoken guesses. Otherwise values are normal.
- How long it stays: it follows the game's target (Status.json "Destination"). It stays while that planet is your target, and also while your target does not change at all (you are landing). If you target another body, or clear the target after having targeted the planet, the list comes back. It also goes back to the list in the next system. Voice "hide the bio overlay" and the settings switch still work, and the Test button now shows the list for 5 seconds and then the planet view.
- Toned down: the "first discovery" lines are now only for Earth-like worlds and the rare giants (water giant, helium rich, class V). Water and ammonia worlds stay as before.
Honest limits: not tried in the game. I rely on the game writing the target in Status.json; if the view disappears too early or never goes back to the list, tell me what you targeted and I will check. The drawing was only tested with a stand-in for the screen (no display here).

## 0.59.1: billions
When an amount reaches a thousand million she now says "1 billion" (like the game) instead of "1000 million", in her spoken values, memories and on the overlay (B).

## 0.59.2: planet view stays while you land, and the value no longer collapses
- Landing: the planet view now stays while you are landing, landed, in the SRV or on foot (the game drops your target when you come down, which used to bring the list back). It also stays while Status.json says you are near that planet. Once you have left the planet and the target is cleared (or you target something else) the list returns.
- Value: after you sampled one life form of a planet with several, the list showed only that form's price (83 million became 6.8 million). Now the planet's value is every life form: real prices for the ones you have identified, an average for the rest. The white flags count the forms you have not finished. The "~" (guess) stays until every form is identified.
Honest limit: still not tried in the game; the hold uses the Status.json flags (landed, gear down, SRV, on foot) and the planet name it reports.

## 0.59.3: planet view goes back to the list when you leave orbit
Once you have been down at the planet (landing, landed, SRV, on foot, or near it) the planet view now ends when you leave its orbit, meaning the game stops naming that planet in Status.json (or names another one). Taking off and staying in orbit keeps it up. Honest limit: not tried in the game; "leaving orbit" is whenever the game stops reporting that planet as the one you are near.

## 0.60.0: overlay colours by galaxy region
The game keeps your codex per galaxy region (Inner Orion Spur, Odin's Hold and so on; 42 in all), so the same species is new again in a new region. The overlay now shows that:
- Yellow text and a yellow flag: you have never found that species in any region.
- Blue text and a blue flag: you have found it in another region but not in this one.
- Orange text and no flag: you already have it in this region (also any form you have just finished sampling).
This is used in the list and in the planet view. Before a form is identified (only the genus is known) the colour follows the best chance: if any species of that genus on the planet would be yellow, it is yellow.
How she knows: every codex line in the journal names its region, and your finished samples are filed under the region you are in (worked out from the system's coordinates). On the first start after this update she re-reads your old journals once in the background to fill the regions in (the "Learn from all my old journals" button does the same). Until a species has a recorded region she treats it as found here, so nothing is wrongly blue.
Honest limits: not tried in the game; the colours were only tested with a stand-in screen. Region names come from the same map as the region announcer, so a system on a border could be filed under the neighbouring region.

## 0.61.0: value ranges, and yellow stays yellow
- Her guess is now a range, from the cheapest to the dearest species that could be there: "probably Bacterium or Stratum, around 1 to 19 million credits". If the possibilities are close in price she says one number. After the surface scan (when the genera are known) the range is over those genera only, and once a species is identified it is its exact price.
- The overlay list shows the same range, for example "~1-19M" (a "~" is a guess; an exact price has none).
- The planet view shows a range for each life form until you take its first sample, then the exact price. With several life forms the list shows the sum of the lows and the sum of the highs.
- Colour in the planet view: a form you have never found anywhere keeps its yellow text while you sample it and after you finish it (the codex line the game writes on the first sample used to turn it orange at once). Blue and orange forms keep their colour the same way. The flag still goes once the form is finished.
Honest limits: not tried in the game. A wide range just means the conditions fit several species; check the planet view for the narrower one after mapping. The box is a little wider (23 instead of 21 text units) to fit the ranges.

## 0.61.1: overlay fits up to twelve signals
A planet can have up to twelve biological signals. The list now shows up to twelve flags (they squeeze closer together if needed), and when a planet has more than four flags its value goes on a second line underneath, so the long ranges ("~45.7-175.3M") are no longer squashed against the flags. Planets with four flags or fewer look the same as before. Honest limit: only drawn with a stand-in screen here; tell me if anything still overlaps on yours (and which text size you use).

## 0.61.2: the overlay goes away when the game quits
When the journal says the game is shutting down (the Shutdown line, written when you quit normally) the biology overlay disappears and she drops what she knew about the system. It comes back by itself once you load into the game again (login or a jump). The overlay is her only overlay window at the moment, so that is all of them.
Honest limit: if Elite crashes or is killed, it never writes Shutdown, so the overlay stays until you load in again or leave the system. Tell me if you want her to also watch for the game's program closing.
