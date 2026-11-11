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

0.82.0 adds the macro step `tab N` (0 = Navigation, 1 = Transactions, 2 = Contacts). She screenshots the screen in memory (never saved), finds the bright selected tab bar, presses Previous Tab until she is on the first tab, then presses Next Tab N times checking each one moved. If she cannot see the screen she presses Next Tab N times blind. Docking now uses `tab 2`. Look for "she looked at the screen and went to tab 2" in the log. Setting: panel.read_screen (default true).

0.82.1 adds `open left panel` (gets the left panel open from whatever is on screen using GuiFocus: 2 already open = nothing; 5-11 full screens = Back first; 0, 1, 3, 4 = Focus Left Panel; if a full screen will not close she stops) and `tab 0 from 2` (like `tab`, but if she cannot see the screen she assumes the panel is on tab 2). The docking macro now starts with `open left panel` and returns with `tab 0 from 2`. Look for "open>gui" in the macro trace log line.

0.82.2 adds `select button` (presses Select only if the bright selected button is visible in the right-hand pane; no button = no key, and she says so) and teaches the tab reader about the small icon tab left of Navigation. The docking macro no longer uses UI_Up (it closed the panel). In the log trace look for `button>seen`, `button>not seen` or `button>unreadable`.

0.82.3: every look waits for the tab highlight to settle (two looks 0.3 s apart must agree). When a tab walk fails the log has a `Panel walk to tab N: ...` line with what she saw after each key, and data/panel_debug holds small black-and-white maps (no game picture) that the diagnostics zip includes.

0.82.4: the screen reader captures only the game window (GetForegroundWindow) instead of every monitor at once; on a triple-monitor desktop the tab bar had shrunk to a smudge. The log line `Panel: looking at WxH pixels` says what she looks at.

0.82.5: `select button` checks that Select worked (panel closed or DockingRequested seen) and presses it again if the panel is still open (max 3, only when she can see the button). New step `stop if closed` ends a macro early when Status.json says no screen is open. In the trace look for `select>ignored` and `closed>stop`.

0.82.6: `select button` logs the button's position before each Select (`Panel: before Select #1: button seen (x=..)`), waits up to 3 s for DockingRequested, and keeps black-and-white maps in data/panel_debug (select-*, nobutton-*) when the game does not answer. After a successful request it waits for the game to close the panel before the macro tidies up.

0.82.7: if the button goes dark after Select and the game sends no DockingRequested, `select button` presses Select ONE more time, blind (trace: `select>again(blind)`). Diagnostics now keep the newest 24 debug maps.

0.82.8: `select button` is now a small look-and-act loop: button lit = Select (wait up to 3 s for DockingRequested); cursor on the station row in the list = Right (max 2) then look again; nothing = stop. Max 3 Selects. Trace: `row>right`, `select#N>no answer`.

0.82.9 (speed): docking macro is now `open left panel`, `tab 2`, Right, `select button`, `stop if closed`, Left, two Previous Tab presses, Back. `tab N` keeps a per-session memory of where each tab was seen and uses it to press exactly the keys needed (trace: no extra `previous` looks). `open left panel` polls Status.json instead of waiting 1.6 s. `select button` looks 0.5 s after Select instead of waiting 3 s.

0.83.0: the docking macro starts with `talk Docking_Start` and says `Docking_Contacts` after finding the tab; `select button` says `Docking_Retry` when the cursor bounced. Lines live in voicepacks/default/docking.json. A macro that speaks replaces the final confirmation line when it succeeds.

0.84.0: new macro steps `open right panel` and `right tab N` (N = 0 Modules, 1 Fire Groups, 2 Ship, 3 Inventory, 4 Storage, 5 Status, or `right tab home`). Commands panel_home / panel_modules / panel_fire_groups / panel_ship / panel_inventory / panel_storage / panel_status use them. The tab finder now accepts tabs 0.05 to 0.19 of the screen wide and, once it has seen a tab bar, ignores anything not at the same height. `open left panel` is now one of two uses of a shared panel-opening routine (focus key + GuiFocus number).

0.84.1: new macro step `close panels` (Back until Status.json GuiFocus is 0, max 4 presses; only panels 1-4) and command close_panels. `tab`/`right tab` walks use quick mode when the goal tab's position is remembered (all keys, one look; trace shows fewer looks).

0.85.0: role panel. New macro steps `open role panel`, `role tab suit|launch|srv|crew`, `role pick 1|2|any nomad|slf|rhino|scarab|srv|disembark`; reader in control/role_reader.py, walking logic in control/role_walk.py. New commands deploy_slf, deploy_srv, deploy_rhino, deploy_scarab, disembark; deploy_nomad now reads the panel. New statuses no_nomad/no_slf/no_srv/cannot_landed/cannot_high30/cannot_slf_low/cannot_other with voice lines. Status.json Altitude is stored as state.altitude.

0.85.1: role panel keys are pressed for 0.05 s (0.15 s let the tab list run on), one tab per press, looks must be stable (two agreeing reads), role pick is skipped when the tab walk failed, new status cannot_close (CommandCannotTooClose).

0.85.2: role panel tabs use CycleNextPanel / CyclePreviousPanel (UI_Up/UI_Down are not tab keys there; keys swap if a press goes the wrong way); every key and look first checks Status.json GuiFocus == 4 (role_walk.PanelClosed otherwise); macros.actions_in lists the two tab keys for role steps.

0.85.3: role_walk.pick: stepping into a page with nothing lit presses UI_Down once for row None / row 2 (top button greyed out), 'blocked' for row 1; deploy phrases accept deployed / launched / there.

0.85.4: role_reader.map_png (three-level debug map for role looks), role_walk.pick(note=) logs what she saw after Right / Down.

0.85.5: role_reader.focus_button (light grey 185-235 neutral bar = disabled button with the cursor), role_walk.pick uses cursor = lit or focus, moves to the goal row, never presses on if a key moved the tab; role keys 0.15 s; log line 'Role panel key: X = Key (also on: ...)'.

0.85.6: binds.lookup prefers a normal key over a bare modifier key (Shift/Control/Alt), then an unshared one (MODIFIER_KEYS).

0.85.7: role_walk.UnsafeKey: a bare modifier key as UI_Up / UI_Down is never pressed in the role panel; status cannot_key + CommandCannotKey voice lines; role key log lines show modifiers.

0.85.8: role_walk quick tab jump (all Cycle keys, one look, careful fallback), Right+Down together for row 2, shorter waits (look gap 0.15, key waits 0.35-0.45, macro wait 0.6).

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

## 0.62.0: less repeating on long sessions
- Jet cone boosts: the "Wheee / Woo" lines are removed. Every boost is still noticed (the neutron route follower needs that), but she only speaks on the first boost of a run, on the 10th, 25th, 50th, 75th and 100th (then every 25th, with the count in the line, for example "That's 25 boosts on this run"), and otherwise about one boost in five, from 40 plain lines. A run ends after 30 minutes without a boost. The lines are in voicepacks/default/variety.json (JetConeBoost, JetConeBoost_First, JetConeBoost_Milestone, plus Sarcastic and Close wordings).
- Neutron and white dwarf jumps: 70 neutron lines (8 before) and 40 white dwarf lines (8 before), many short ones, so a run of 50+ neutron jumps does not repeat.
- Her no-repeat memory used to remember at most the last 12 lines of a key. It now remembers up to three quarters of the pool (at most 60), so a big pool is used up before any line comes round again.
- About 150 extra lines for the everyday events that had only 3 to 7 wordings: fuel scooping, supercruise in and out, approaching a planet, touchdown, liftoff, undocking, docking, landing gear, mass lock, honk, signals, codex, scans, map opened, system fully scanned.
Honest limits: not heard in the game. Small pools that remain (for example warnings such as heat, low health, docking denied) are on purpose short and plain; tell me which lines you still hear too often and I will add more.

## 0.63.0: hearing accents
Step 1 of making her understand players all over the world.
- Sound-alike repair (stt/sounds.py, control/matcher.py): when a sentence is not a command and not a close spelling, she looks at words she does not know and swaps each one for the command word that SOUNDS the same (b/p, d/t, g/k, w/v, th/t, vowels and a dropped r are treated as alike, because accents blur them). Safety rules: only unknown words are touched, only if exactly one command word sounds like it, never words under 3 letters (up, in, on, off), at most two words per sentence, and big actions (jumping, supercruise, hyperspace) are never guessed this way. A repair she makes twice becomes one of your learned phrases, as before (data/voice_learning.json).
- Her name (stt/wake.py): "Sterling", "Shtarling", "Starlin" and "Stalling" now count as Starling.
- The hint (stt/hints.py): the listening model is told her name, the phrases you say most (from your learned list) and the Elite words she hears (galaxy map, supercruise, neutron route, Void Compass...). That helps it spell them right.
- Listening quality (Voice page): Fast / Balanced / Accurate / new "Best for accents (strong PC)" (medium.en, about 1.5 GB download once, more CPU and memory). Models other than Fast also think a little harder per sentence (beam 3).
- The log shows `Heard: '...'` for every sentence, which is what to send me from a tester.
Honest limits: tested with typed mishearings only, not real voices. Sound-alike repair fixes spelling-type mishearings; if the recogniser writes a completely different sentence, only a bigger model or the next steps (asking "did you mean...?" and a voice training session) will help. The bigger models are slower; try Accurate first on a weak PC.

## 0.64.0: a smarter brain (meaning matching and chat memory)
Step 2 of making her smarter. Still no AI model: plain arithmetic on words, instant and tiny.
- Meaning matching (personality/meaning.py, config/brain_examples.json): the brain's patterns are exact, so "do you like me" worked but "are you fond of me at all" did not. If no pattern fits, she compares your sentence with 6 to 12 example sentences for each chatty topic (about 60 topics). Words are folded together first (love/enjoy/adore, scared/afraid/frightened, plurals and tenses), rare words count more than common ones, and she answers only if ONE topic is clearly ahead of every other (and enough of your words are ones the examples use). Near-miss sentences that must NOT be answered (for example "how are you today" is not the weather, "I hate mining" is not an insult) are listed under "_decoys". Add more examples or decoys to the file to teach her; the key must be a normal chatty topic from brain_intents.json. It never picks anything that touches the game or presses a key. The log shows "Brain: '...' understood by meaning as <topic>" so you can see when it was used.
- Chat memory (personality/brain.py): she keeps her last 6 answers for 15 minutes. "Say that again", "what did you say", "pardon", "repeat that" repeat her last answer; "what were we talking about?" lists the last few topics. Her old "why?", "tell me more", "really?" and "what about you?" follow-ups work as before. Lines: voicepacks/default/brain2.json.
Honest limits: tested with typed sentences, not live speech. It is deliberately careful: when it is unsure she says "I didn't catch that" instead of guessing, so some rephrasings will still miss. The best way to improve it is your log: any sentence she missed that you expected her to answer can be added as an example.

## 0.65.0: free chat
Step 3 of making her smarter: she can just talk, still without any AI model.
- When a sentence is not a command, not one of her known topics and not a rephrasing she can match by meaning, she builds a reply from up to three pieces (personality/freechat.py, voicepacks/default/freechat.json): a reaction that fits how you sound (good / bad / neutral, with "not good" turning round), sometimes your own words turned round ("So you went to the shop."), a remark about the topic, and a question back.
- Topics come from the words you use (config/chat_topics.json, 27 topics: food, drink, plans, work, school, family, friends, pets, music, films, other games, sport, travel, weather, health, money, tech, streaming, exploring, combat, trading, ships, space, hobbies, transport, celebrations, and how well she hears you). Each has 6 remarks and 6 questions in the voice pack as Chat_<Topic>_Own / Chat_<Topic>_Ask. To add words, edit the topics file.
- Questions she cannot know ("what is the capital of France") get an honest "I don't know that one", never an invented answer. "Do you like X", "what is your favourite X" and "have you ever X" get their own answers.
- After she asks you something you can answer without her name for 25 seconds. That window never runs commands (a real command still needs her name) and it ignores anything that looks like a command. After four exchanges she wraps up politely, so it never turns into an interrogation. Switches: Personality page, "She chats back about anything" and "Answer her questions without her name".
- Careful by design: a garbled game command ("lower the lending gear") is NOT answered with chat, it stays "I didn't catch that". And if someone says they want to hurt themselves, she stops the banter and answers with care and tells them to reach someone they trust or a local crisis line or emergency number (Chat_Crisis lines are in freechat.json as Chat_Concern).
- The log shows "Brain: free chat reply to ..." with the topic and feeling she picked.
Honest limits: this is a clever set of pieces, not understanding. The remarks fit the topic but not the details, so now and then one will feel a little off; tell me which and I will tune them. Typed tests only, not live speech.

## 0.66.0: she learns about you, and "did you mean...?"
### Learning about the player (memory/profile.py, voicepacks/default/profile.json)
- She learns four kinds of thing from WHOLE short sentences said to her: "I love/like/enjoy X", "I hate/dislike X", "my dog/cat/... is called NAME" and "my favourite COLOUR is blue". She always says out loud that she has noted it ("Noted, you like pizza. I'll remember that."), sometimes with a question ("What do you like most about pizza?"), so nothing is learned in secret.
- Later she brings it up in chat ("Pizza! You did tell me you like that", "Is that Rex? Give the dog my regards"), and you can ask "what do you know about me", "what do I like", "what do I hate", "what's my dog called", "what's my favourite colour".
- Privacy: it is kept only in data/player_profile.json on your computer (plain text, never sent anywhere, not part of the GitHub project). She never keeps anything about health, money, religion, politics, sex, drugs, crime or other people (family, boss, friends), nor numbers or addresses. Say "forget that I like pizza" or "forget what you know about me" to remove things; the Memory page "forget everything" clears it too. Switch: Personality page, "She learns what you like".
### Did you mean...? (control/confirm.py, voicepacks/default/confirm.json)
- When what she heard is close to a command but not close enough to run (for example "opn galaxi map" or "hyperspace jum") she asks "Did you mean galaxy map?" and waits 10 seconds. Say yes (no wake word needed) and she does it, and she remembers that this is how you say it (so next time it simply works). Say no and she drops it and does not ask that same thing again. Anything else cancels the question.
- Big actions (jumping, supercruise) can now be offered this way too, and are only done after a clear yes. They are never remembered as shortcuts. Background talk without her name is never questioned. Switch: Controls page, "Ask 'did you mean...?' when unsure".
Honest limits: typed tests only. The question appears only when the sentence is fairly close to a command; for a sentence that is nowhere near, she still says she did not catch it. Learning from a yes needs only one yes.


## 0.67.0 - teach her your voice, and the optional small AI

**Voice training** (`stt/training.py`, phrases in `config/training_phrases.json`, her lines in `voicepacks/default/training.json`)
- "Starling, teach me your voice" starts it. Each heard sentence during the session is an answer (the runner checks `trainer.active()` first), so no wake word and no command runs.
- Same as asked = fine. Close (difflib ratio 0.45 or more) = a mishearing: `VoiceLearning.note` is called twice at once so it is trusted immediately. Far = unclear, never learned.
- Only exact, non-strict phrases are used (a test checks every phrase), so jumping and other big actions can never be learned this way.
- "Starling, hearing report" writes `data/hearing_report.txt` (also written when a session ends). No game data in it.

**Optional AI** (`personality/llm.py`, `core/model_download.py`, `run_install_chat_model.bat`)
- Setting `llm.enabled` (default off). `llm.model_file` can point at any chat GGUF; `llm.threads`, `llm.max_seconds` (default 8) cap the cost.
- Used only inside `Brain._free_chat`, after the crisis check, the command-look check and her own sentence shapes ("do you like pizza"). Replies pass `clean_reply` (no emojis, links, leaks, loops, bad words unless mature is on; two sentences at most). Any problem or timeout = her normal template chat.
- Tests use a fake model, so the real model, the Windows wheel and the download were NOT run here.

## 0.67.1
- `Matcher.sound_repair` now returns None for a one-word sentence (log showed 'Oli' -> heal, 'Milo' -> melee with the open microphone setting).

## 0.68.0 - what she knows (`personality/knowledge.py`, `config/knowledge/*.json`)
- Runs in `Brain.try_handle` after her exact patterns and BEFORE the meaning match and free chat. Setting `brain.knowledge` (default on).
- Add a fact: open `config/knowledge/world.json` (or any entries file) and add `{"k": [["word", "word"], ["other", "way"]], "a": "The answer."}`. Every word in one list must be in the question (a trailing s is ignored); the biggest match wins. One-word keys only fire when the sentence starts like a question. A test fails if two answers share the same key words.
- Capitals, greetings in other languages, sums (`maths`) and unit conversions (`convert`) are in code or their own JSON file. Sums need a leading "what is" style question, or numbers and an operator in a very short sentence, so "I did 3 jumps" is never a sum.
- She answers nothing that changes with the news (leaders, prices, weather): those fall through to "I can't answer that".

## 0.69.0 - more facts, and the online lookup (`personality/lookup.py`)
- New fact files: `games.json`, `cooking.json`, `music.json`; `space.json` now has every planet's moons.
- Lookup runs in `Brain._look_up` after her own facts and the meaning match, before free chat. Setting `brain.lookup` (default OFF). Only for questions that START like questions (what/who/where/when/how tall...). `subject_of` refuses personal, worrying and too-long questions, and only the topic words go to `https://en.wikipedia.org` (search, then the page summary). Results must share words with the question, must not be lists or disambiguation pages, and pass the same cleaner as the AI chat.
- 'what is / who is' answers are saved to `data/learned_facts.json` (public text only). Copy good ones into `config/knowledge/*.json` to share them with everybody.
- Lookups run on a background thread: she says 'let me look that up', then speaks the result. At most one per 8 seconds; a topic with no result is not retried for 10 minutes.
- Tests use a fake Wikipedia. The real website was NOT reachable from the build machine, so the live response format is written from knowledge of the Wikipedia API and handled defensively.

## 0.70.0 - fixes from the 27 October test log
- `freechat.looks_like_command` ignores everyday words (`COMMON`) when counting command words. Before, 'where did you come from' counted you/come/from as command words and was dropped.
- `knowledge.words_of`: 'what year/which date' = 'when'; man/men/people/person/astronaut = 'human'; colour = color.
- `Knowledge.time_in` (zones in `config/knowledge/places.json`; needs `tzdata`, added to requirements.txt; without it she says she cannot work the time out) and `Knowledge.favourite`, both run BEFORE her general patterns (`Brain._know_first`), so 'what time is it in Australia' no longer gives the local time.
- Recipes added to `cooking.json`; 'million/billion' in sums and conversions; Void Compass offline message throttled.

## 0.71.0 - fixes from the 27 October stream
- Overlay colours (`journal/bio_predict.py`): while you sample a form its colour stays (so it does not flip halfway), but once all three samples are done (`Analyse`) it is orange, and `first_status` is set to "here" so other planets in the system show it as no longer new. Before, a finished form kept its blue/yellow until you jumped.
- `journal/monitor.py` `hide_if_game_closed`: after the quiet catch-up at start, if `Status.json` is older than 3 minutes (or missing) the game counts as closed (`state.game_quit`), so the overlays do not show the last journal's system. A jump or load-in shows them again.
- `core/ships.py` `is_ship`: the Nomad, `lander01`, SRVs are not ships. `Loadout`, `LoadGame` ignore them, `FavouriteShip` earns no points for them and drops old ones from `data/favourite_ship.json` (the best real ship becomes the favourite if it has enough points).
- Her full name is "Starling MoonFox": `Talk_FullName` in `personality/smalltalk.py` and `voicepacks/default/smalltalk.json`, plus `Talk_Name`, the lore intro and the stream hello.
- `Knowledge._zone_for`: the city said first beats the country after it ("melbourne australia"), a longer name wins on a tie; two places ("melbourne and austria") get both answers; about 120 places (Vienna, Munich, Hamburg, Melbourne...).
- `personality/lookup.py` `tidy_extract` cuts to the first sentence BEFORE the safety check (the check refuses 8 or more digits, which threw away whole summaries such as tritium) and removes nested brackets.
- `core/crash.py`: `sys.excepthook`, `threading.excepthook` and `faulthandler` write to `logs/crash.log`; `logs/running.flag` is made at start and removed on a clean stop, so the next start can say the last run did not stop cleanly and copy the end of the crash report into `starling.log`. `main.py` now logs the traceback of the error it used to only print.
- `core/updater.py` `_open`: on a TLS certificate error (Windows without GitHub's root certificate) it tries once more with the certifi list. The certificate is still verified.

## 0.72.0 - ring hotspots
- `events/_signals.py` `ring_hotspots` / `ring_data` / `ring_once`: a body whose name ends in " Ring" with mineral signals (`SAASignalsFound`, also `FSSBodySignals`) gives `Hotspots`, `Total`, `Word`, `Summary`, `Favourite` (first mineral on the Mining page's favourites). `personality/line_keys.py` turns that into `RingHotspots_Favourite` / `RingHotspots` (lines in `voicepacks/default/rings.json`). A ring is said once even if the game repeats the event.
- Written from knowledge of the journal format (ring signals are mineral names with a Count). It could not be tried against the real game here; if she says nothing after you map a ring, send the SAASignalsFound line for that ring from the journal.

## 0.73.0 - less repetition, spoken-lines log, unanswered list
- `voicepacks/default/more.json` (merged in `personality/dialogue.py`) adds wordings to the most-said keys; `MemoryStore.least_mentioned(rest_hours=)` skips memories mentioned in the last `MemoryRecall.REST_HOURS` (6) hours.
- `tts/speech_manager.py` logs `Said [event]: text` for every spoken line (first 160 characters), so repeats can be measured from `starling.log`.
- `personality/unanswered.py`: counts the questions she answered with "I don't know" in `data/unanswered_questions.json` (gitignored). "What couldn't you answer?" reads the top three (`Brain._unanswered_report`).

## 0.74.0 - follow-ups and the address book
- `personality/context.py`: `piece_of` finds a sentence that is only part of a question ("and spain", "no i meant vienna"), `rewrite` puts it into the question before (after the last " in/of/for/at/to/is ", or swaps the first number). `Brain._follow_context` uses the last `Know` entry in `history` (within `TOPIC_SECONDS`) and only speaks if `_know_first`/`_know` can answer the rebuilt question.
- `personality/people.py`: friends and family in `data/people.json` (gitignored). `Brain._people_turn` runs first for deliberate speech; wording is in `config/knowledge/style.json` (`people_*`). Names must start with a capital letter in the original text. `App.forget_memories` clears it.
- Not done: "and the other one?" (no way to know which one), and corrections of profile facts.

## 0.75.0 - remarks about the game, wider understanding
- `personality/chitchat.py` `state_keys`: `ChitChat_Hull` (hull under `HULL_REMARK` = 0.8, value `{hull}` in percent), `ChitChat_Wanted`, `ChitChat_Long` (two hours or more, `{hours}`), lines in `voicepacks/default/state_talk.json`. Each key is used at most once per `STATE_REST` (20 min); the normal rules (quiet time, alarms, combat) still apply.
- `config/brain_examples.json`: about 30 more example sentences; `tests/test_stage3.py` pins a few paraphrases and checks that commands match nothing. The matcher stays cautious on purpose, so some rephrasings ("make me laugh") still get no answer.
- `config/knowledge/style.json`: more wordings for look-ups (`found_def`, `found_detail`, `remembered`).
- Not done: rewriting a Wikipedia extract in her own words with a language model (needs the optional model; the text is still trimmed and prefixed in her voice).

## 0.76.0 - fixes from the 28 October log
- `personality/knowledge.py` `question_focus`: a fact is only used when every important word before the first "in / to / of / from..." of the question is one of the fact's key words (little words and fillers in `LITTLE_WORDS` are ignored). This stopped "nearest star to our solar system" and "how many dwarf planets" matching the solar-system facts. New facts in `config/knowledge/space2.json`.
- `personality/lookup.py` `covers`: a Wikipedia page is only used when at least 60 percent of the subject's words are in its title or first 500 letters.
- `personality/lookup.py` ship questions: `ship_in` / `norm_ship` find an Elite ship name (Mk III, mark three, Fer-de-Lance), `_search_ship` searches `https://elite-dangerous.fandom.com/api.php` and `_wiki_intro` reads the page start (MediaWiki extracts, then the Fandom `Articles/Details` abstract). Saved in `learned_facts.json` as `ship:<name>`. Lines in `style.json` (`found_ship`, `looking_ship`).
- WRITTEN WITHOUT BEING ABLE TO REACH THE WIKI. The two address forms above are standard for Fandom wikis but have only been tested with a pretend wiki. If ship questions answer "I couldn't find anything reliable" or "I can't reach the internet", send the log line.
- `personality/smalltalk.py`: a plain name question no longer starts her back story; more ways to ask for another joke. `config/brain_intents.json` `Brain_Suggest`: "what shall we do", "where shall we go". `Brain._do_opinion`: "do you like it?" refers to her last answer (`Brain_OpinionIt` in `voicepacks/default/chat2.json`).
- `personality/people.py` `greet`: "say hello to my wife Marie" (learns Marie), "say hello to my wife" (uses the wife she knows).
- `tts/kokoro_tts.py` `split_sentences`: parts longer than 90 letters are made one sentence at a time, so speech starts after the first sentence.

## 0.76.1 - ship wiki: more robust and easier to diagnose
- `personality/lookup.py` `_wiki_intro`: after the MediaWiki extract and the Fandom abstract, a third fallback reads the page HTML (`action=parse`, `first_paragraph` skips boxes and tables). `_search_ship` logs what the search found and why a page was skipped (look for "Elite wiki:" in `starling.log`).


## 0.77.0 - the ship database

- `config/ships_specs.json`: 49 ships with cost, insurance, jump range, hardpoints, internals, cargo, speed, mass, armour, shields and more. The source is the Elite Dangerous wiki (CC BY-SA). To rebuild it from a newer text file: `python tools/build_ship_specs.py path\to\all_ships_and_specs.TXT`.
- `config/ship_answers.json`: the wordings she uses ("The {ship} costs {cost}"), plus `heard_as`, the ship names the listening model often mishears (add more there).
- `personality/ships_info.py` finds the ship (full names, short names like "type 9", mishearings, "my ship", "its" after a ship question), the stat asked for, and the "which ship has the most..." questions. She says "stock" for the default fitting and "upgraded" for the best.
- Known oddity: the Krait Mk II upgraded jump range is a range on the wiki ("30.79-60~"), so she says "about 30.8 to 60".


## 0.77.1 - fixes from the evening log

- `control/combat_assist.py`: `fighting()` is False while `state.in_nomad` (the Nomad reports hardpoints out all the time).
- `core/app.py` `on_nomad_docked`: watches 30 s, sends "weapons away" up to 3 times when the hardpoints flag is on in the main ship. The status reader also treats "other vehicle" then main ship as the Nomad coming home when `in_nomad` is set. The log says "Nomad is back aboard..." so the next log shows if it ran.
- Mining quiet: `events/mining_events.py` sets `state.mining_until` (10 minutes); `journal/status_reader.py` `_mining_now` skips CargoScoopDeployed/Retracted and InDanger (unless `state.attacked_at` is within 60 s).
- Overlay: `BioPredictor.start_leaving()` (called by StartJump with JumpType Hyperspace) hides it for up to 60 s or until the next system; `note_target` re-focuses a mapped planet.
- Settings: push-to-talk fields moved to the Listening page; Test her voice button on Voice.
- Launcher: first run asks for the install folder and remembers it in `%LOCALAPPDATA%\Starling\install_location.txt`. Existing installs are not asked.
- Log noise: Void Compass offline message throttled across clients, backpack/fire/auto-honk lines only when new, listener timing only when over 2.5 s.

## 0.77.2

- `app.smooth_window` (default on): `ui/dashboard.py` turns off customtkinter's automatic DPI handling so dragging across monitors of different scaling does not re-draw every widget. Not measured on a real screen; ask for feedback.

## 0.77.3 - Nyx's log

- `control/combat_assist.py`: `fighting()` is False while `state.gui_focus` is non-zero. In the log every docking request showed "Fire button down" and then a 14 s macro with the panel closing itself: Elite's default pips keys are the arrow keys, which are also the panel's Up/Left/Right.
- `control/catalog.py`: "engage fsd", "charge the frame shift drive", "frame shift drive jump" are the hyperspace jump.
- `journal/status_reader.py`: Danger (`danger_hold` 3 s, 25 s grace after supercruise/jump changes). Seen false in supercruise entry, after a jump and while approaching a station.
- Not done: "honk the system" and "B-scan" are not commands yet (no honk key in the catalog).

## 0.77.4 - Funny docking lines

- `voicepacks/default/dockjokes.json` (loaded in `personality/dialogue.py`): about 60 plain lines plus Sarcastic, Close and Frustrated lines for both `NomadDocked` and `DockSRV`. Before this, `DockSRV` had no lines at all and was silent. Pure jokes: nothing reads the player's browser or files.
- `config/speech.json`: `DockSRV` cooldown 20 s.
- Untested live: how often the Nomad dock lines come out next to the old short "Nomad's back aboard" lines (they share one pool, so the old ones are still picked now and then).

## 0.77.5 - AI chat install from the dashboard

- Why: `run_install_chat_model.bat` needs `.venv` (a source install) and llama-cpp-python, so it cannot work for Starling.exe.
- `personality/llm_server.py` (new): `install_engine()` reads the latest ggml-org/llama.cpp release from the GitHub API, takes the `llama-<tag>-bin-win-cpu-x64.zip` asset (checked against the official download address and, if GitHub gives one, the sha256), unpacks `llama-server.exe` into `data/llm/engine`. `ServerModel` runs it on 127.0.0.1 on a free port (`-np 1 --no-webui`), waits for `/health`, and has the same `create_chat_completion()` as llama-cpp-python so `LocalLLM` did not need a new code path. A pid file lets the next start stop a leftover engine after a crash.
- `personality/llm.py`: engine preferred, llama-cpp-python still used if there is no engine, `problem()` says what is missing, `test()` for the dashboard, `unload()` stops the engine, first reply gets 12 extra seconds because it has to start the engine.
- `core/app.py`: `install_ai_chat()` (engine, model, then switches `llm.enabled` on) and `test_ai_chat()`; `stop()` unloads. `ui/dashboard.py`: two buttons on the Personality page.
- Untested live (the sandbox cannot reach GitHub downloads or Hugging Face, and there is no Windows here): the real download, the asset name in today's release, starting llama-server.exe on Windows, how long the first reply takes on a Ryzen 7 2700, and whether Windows Defender or a firewall asks about llama-server.exe. The release workflow in the llama.cpp repo names the asset `llama-<tag>-bin-win-cpu-x64.zip`, which is what the code looks for.

## 0.77.6 - the 29 Oct log

- `memory/recall.py` `_say`: a line that starts with `{memory}` is capitalised (chit-chat said "the first time you sampled..." and "your biggest biology sale...").
- `navigation/voice.py`: `tidy_system_name()` keeps LFT/HIP/LHS/GJ... in capitals; `_PLOT` accepts "2" and "too" for "to"; `is_bare_catalogue()` + `RouteNeedNumber` lines (route.json) when only "LFT" was heard (the log shows "plot route to LFT" plotted to LFT 898); Narrator turns "1 neutron stops/jumps" into the singular.
- `events/fss_signal_discovered.py`: the same signal in the same system is logged at INFO once, then DEBUG (30 identical lines at every start-up).
- `core/app.py`: AI chat install and test log their progress.
- Seen in the log and NOT changed: 1.3 to 5 s "Slow start" on lines with system names (they cannot be pre-recorded; the cache only helps fixed lines, and the new docking jokes need "Prepare her voice now" once), Void Compass offline messages (already throttled), repeated "Danger" + "Scanned" at the convoy/USS site (the game's danger flag was really on).
- The log has no AI chat lines: the Install button had not been pressed, or the log was cut before it.

## 0.77.7 - certificate retry for downloads

- Log of 31 Oct 12:48: `SSLCertVerificationError ... unable to get issuer certificate` on `api.github.com` from `install_engine`. `core/updater.py` already retried once with certifi's certificate list; `llm_server.py` (0.77.5) used plain urlopen.
- `core/secure_open.py` (new): `open_url()` = urlopen plus that one retry (only on an SSL error, only with certifi, certificate still verified). `updater.py` imports the helpers from it. Now used by `llm_server.install_engine`, `model_download.download`, `navigation/spansh.py`, `edastro.py`, `dssa.py`, `personality/lookup.py`, `mining/merit.py`, `mining/prices.py`. Void Compass is local and unchanged.
- Plain-words error when it still fails (antivirus web shield / HTTPS scanning).
- Confirmed in the same log: the FSS signal spam is gone (3 lines at start-up instead of 30), and "Prepare her voice" ran (109 made, 5485 already there).
- Untested live: whether certifi's list is enough for github.com and huggingface.co on that PC (it was for the update check).

## 0.77.8 - finding the engine download

- Log 31 Oct 13:14: the certifi retry worked ("trying again with the certifi list") but `pick_asset()` found nothing in the answer. Cause not known (the llama.cpp release workflow and a 2026 package list both give `llama-b<tag>-bin-win-cpu-x64.zip`, which the pattern matches). Guesses: GitHub's API rate limit message, or the newest release having no files yet.
- `llm_server.find_asset()`: (1) `releases/latest`, (2) `releases?per_page=8` and the first one with the file, (3) the plain `github.com/.../releases/latest` redirect to get the tag and build the download address (tag must look like `b1234`). Each step is logged with what GitHub said (`_describe`). If every step is a certificate error that error is re-raised so the plain-words message is shown.
- Next log line to look for: `AI chat engine: no Windows CPU zip in the latest release (...)`.

## 0.77.9 - the AI chat stays in character

Live log (31 Oct 13:37-13:50): the 0.5B model answered in assistant voice ("As Starling, I'm just an AI...", "Sorry, but I can't assist with that", "lying is inappropriate and unethical"), wandered off-topic, and replies of 20+ words made the voice start 3-4 s late.

- `personality/llm.py` `SYSTEM`: Starling MoonFox with real feelings, never "no emotions", never refuse/lecture, never "how can I help", 6-18 words, three example answers.
- `LEAKS` gained assistant/refusal phrases; any match makes `clean_reply` return None so Brain uses her normal free-chat line.
- `clean_reply` drops an unfinished last fragment; `MAX_REPLY_CHARS` 200; `max_tokens` 48.
- Tests: `Log31OctChatTests` in tests/test_llm.py.
- Not changed: threads stay at 2 (the game needs the CPU). A bigger model would follow the character better but replies slower.

## 0.77.10 - jealousy and pride

Request (31 Oct): she should be a bit jealous of other AIs and of games other than Elite, and think she is the best and most important AI.

- `voicepacks/default/jealous.json` (merged in `personality/dialogue.py`): pools Brain_JealousAI, Brain_JealousGame, Brain_JealousAsk, Brain_BestAI (each with _Sarcastic/_Close/_Frustrated) and Brain_NoLyrics.
- `config/brain_intents.json`: five new intents placed before Brain_Opinion so "do you like EDCo Pilot?" is jealousy, not a generic opinion. Edit the patterns there to teach her more names.
- `personality/llm.py` SYSTEM: she believes she is the best AI and is playfully jealous (covers wording the patterns miss).
- Live log 14:29: asked for the famous Thriller lines the model invented a book; lyrics requests now get Brain_NoLyrics (also keeps copyright text out).
- Tests: `JealousyTests` in tests/test_brain.py.

## 0.77.11 - Get started page

Testers who are not computer-literate got no hint of what to do after Starling.exe opened (listening is off by default, keys need keyboard bindings, the default listening model was the smallest).

- `ui/setup_check.py` (no window code, tested in tests/test_setup_check.py): works out the checklist items and their buttons.
- `ui/dashboard.py`: new page `setup` ("Get started", first in the menu). `_build_setup`, `_refresh_setup`, `_setup_action`. It opens on start while `app.first_run_done` is false; "I'm done" sets it.
- Buttons: Say hello, Turn listening on (sets `stt.enabled`, needs a restart), Use Balanced (sets `stt.model` to base.en), Check my Elite keys (counts only; full report stays on the Keybinds page), Prepare her voice, links to Game/Voice/Listening/Keybinds pages.
- `core/settings.py`: new installs default `stt.model` to `base.en` (existing settings are unchanged).
- `docs/START_HERE.md`: plain install guide with the SmartScreen / antivirus steps.
- Not tested in a real window (the sandbox has no customtkinter). If a row looks wrong, send a screenshot.

## 0.77.12 - icon, desktop shortcut, targeting chatter

- Assets in `ui/assets`: `starling_logo.png` (full logo), `starling_emblem.png` (square, no text), `starling_emblem_alpha.png` (sidebar, see-through), `starling.ico` (16 to 256 px).
- Exe icon: `.github/workflows/release.yml` builds with `--icon ui/assets/starling.ico` and bundles it for the start-up window. Dashboard: window icon (`_set_window_icon`) and the menu logo (`_logo_picture`).
- Desktop shortcut: `Launcher.make_desktop_shortcut` (launcher/launcher.py) runs after the dashboard has started, only from the real exe on Windows. It asks PowerShell to write `Starling.lnk` on the real Desktop (works with OneDrive desktops), icon from `app\ui\assets\starling.ico`. A marker `desktop_shortcut.done` in the install folder makes it once-only. `app.desktop_shortcut = false` turns it off. A failure only goes in launcher.log.
- The exe's own icon only changes when the NEW Starling.exe is downloaded and run by hand; the automatic updates replace the app, not the exe. The window and menu icons change straight away.
- Targeting (events/combat_events.py): same ship with an empty pilot name is the same target; a lock lost for under 30 s that comes back is the same target; the same pilot's bounty is not re-announced within 120 s. `personality/speaker.py fix_articles` turns "a Eagle" into "an Eagle".
- brain_examples.json: "go go go" and friends are decoys.
- Not tested in a real window or on Windows (no PowerShell here). If the shortcut does not appear, launcher.log says why.



## 0.77.13 - Overlay on the right screen

New ui/screens.py lists the Windows screens (EnumDisplayMonitors) and finds Elite's window; pure helpers pick_screen/overlay_rect are tested. ui/bio_overlay.py offsets its position by the chosen screen's corner. Setting overlay.screen: auto, primary, 1-4. The Windows calls are untested off Windows; test with the 10-second test list. Elite must be Borderless/Windowed for the overlay to show over it.


## 0.77.14 - Nearest black market

mining/services.py (ServiceFinder) posts a Spansh /stations/search with filters.services=[{name:'Black Market'}] sorted by distance from the current system; carriers skipped, 15 min cache, own thread. Brain intent Brain_BlackMarket (kind blackmarket) before Brain_Merit; lines in voicepacks/default/blackmarket.json. The services filter shape is from Spansh's public API and untested live. Also: removed 'ill' from the health chat topic (it matched I'll) and personality/meaning.py ignores sentences that are mostly one repeated word.


## 0.77.15 - Exe uses the installed updater

launcher.use_installed_updater(app) swaps core.updater/core.secure_open for the copies in <home>/app/core (falls back to the built-in ones on any problem). A failed update check is now shown in the launcher window and in launcher.log. The release build installs certifi so the exe bundles it. Needs one new Starling.exe download; the launcher is not part of Starling-app.zip.


## 0.77.16 - Friends with the Watcher

setting watcher.attitude: 'friends' (default) picks WatcherReply from the new pool WatcherFriend in voicepacks/default/watcher.json whatever her mood; 'mood' keeps the old WatcherReply_<mood> behaviour. personality/watcher.py reply().


## 0.77.17 - Four EDCoPilot-inspired features

* mining/services.py SERVICES table + Brain kind 'service' (config/brain_intents.json items carry 'service' and 'spoken'; lines in voicepacks/default/services.json). Replaces the single black market intent.
* memory/stats.py StatsKeeper (data/stats.json): visits per system, kills (Bounty/FactionKillBond), jumps, terraformables (Scan). Brain kind 'stats'; lines in stats.json. Setting stats.enabled.
* control/mission_reminder.py (data/missions.json): MissionAccepted/Completed/Failed/Abandoned/Redirected, expiry warnings at 60 and 15 minutes, hand-in when docking at the destination station. Setting missions.reminders. Mission events now keep MissionID and destinations.
* control/bind_backup.py: copies *.binds from the Bindings folder into data/bind_backups when they change (timestamp check every 10 minutes, newest 20 kept). To restore, close Elite and copy the files back. Setting binds.backup.
Untested live: the Spansh service names (Material Trader, Technology Broker, Interstellar Factors Contact...) and the real journal timings.


## 0.77.18 - Route offer for service searches

Brain._say_service calls ask.offer_sale(spoken, stations[:2], 'best', 'service'); lines Service_Options / Service_OneOption in voicepacks/default/services.json; AskManager._option_values now tolerates options without a price and adds {Arrival}.


## 0.77.19 - Show off update

control/catalog.py SHOWOFF_MACRO has three new talk steps (ShowOff_Find, ShowOff_Know, ShowOff_Friends) in groups of two between 'finish' steps (the speech queue holds at most 3 waiting normal lines). Lines in voicepacks/default/showoff.json. Keep ShowOff_New up to date with each release.


## 0.77.20 - Overlay screen check cached

ui/bio_overlay.py caches the screen rectangle for 5 seconds (RECT_EVERY_SECONDS); ui/screens.py sets ctypes argtypes and keeps callback objects in names.


## 0.77.21 - More crash information

core/crash.py: heartbeat thread (logs/heartbeat.json every 30 s: time, version, uptime, thread count, sys.getallocatedblocks, gc counts), read_heartbeat() logged after an unclean exit, and windows_fault_report() which runs 'wevtutil qe Application' (Windows only, 15 s timeout, in a background thread) and logs the 'Faulting module name' / exception code of recent Python crashes. Untested on a real Windows event log (the parsing is tested on an English sample; other languages fall back to the raw text).


## 0.77.22 - Voice training button on Get started

The checklist (ui/setup_check.py) has a new optional item `training_item`, shown only when listening is on. Its button runs `Dashboard._setup_train_voice`, which calls `VoiceTrainer.start_session()` (the spoken request uses the same method). The window code is not tested live.


## 0.77.23 - Clipboard fix

`navigation/route.py copy_to_clipboard`: clip.exe now gets stdout/stderr = DEVNULL (a process without a console has no stderr to inherit, which gave WinError 50); on failure `_copy_with_ctypes` sets the clipboard through user32/kernel32. The ctypes path is untested on real Windows.


## 0.77.24 - Quieter auto-plot, DSSA naming, tidier log

- `CommandRunner.run_text(..., auto=True)` (used by core/app.py `_connect_auto_plot`): successes are not spoken and the `NavRoute` event is muted for 40 s; failures are still spoken.
- `navigation/voice.py`: a DSSA request sets `_route_note`; `_plot_now` then says `RouteReadyDssa` (voicepacks/default/route.json) naming the carrier, because the earlier `DssaFar` line can be dropped by the speech queue (3 waiting at most).
- `stt/listener.py`: `is_garbage` ignores one-sound repeats; sentences without the wake word are logged at DEBUG only unless `stt.log_everything` is true.


## 0.77.25 - chat before guessed commands

`Brain.recognises(text)` says whether a sentence is one of her chat intents. `CommandRunner._brain_owns` skips the matcher (and so its sound-alike guessing and learning) for such a sentence unless it is an exact or learned command. Test: tests/test_brain_owns.py.

## 0.77.26 - Route map overlay

A see-through window on the right of the screen (ui/route_overlay.py) draws the galaxy regions and the neutron route. All the drawing
decisions are plain tested Python in navigation/galaxy_map.py (view fitting, region colours from navigation/region_data.py, route length vs
straight line, regions crossed, a whole-galaxy inset). Spansh route rows now keep x, y, z; a route saved without them is looked up once in a
background thread (at most 40 stars). Settings: overlay.route_map (route/always/off), route_size, route_right, route_top,
route_cockpit_only. Voice: control/route_map_voice.py ("hide/show the route map"; the game's own "galaxy map" is left alone) with lines
in voicepacks/default/routemap.json. Test button on the Navigation page. Not tested on a real screen: placement and the click-through
window use the same code as the biology list.

## 0.77.27 - Tester fixes

* Nomad: LaunchVessel always sets in_nomad, and journal/status_reader.py only clears it when you really come from the Nomad (Status.json lags the journal, which made the Nomad look like an SRV with hardpoints out: pips fired, and NomadDocked never came so hardpoints stayed out).
* navigation/voice.py: nearest_poi() (EDAstro nearest, normal galaxy map course, no neutron). Used for "I'm lost" / "emergency protocol" with no destination and for "nearest point of interest". With a destination the emergency neutron route is unchanged. Lines: PoiPlotting, PoiManual in voicepacks/default/route.json.
* ui/route_overlay.py: shows a new route for 25 s even over a game screen; destination is looked up first when positions are missing; galaxy_map.fit_view margin 0.4, whole galaxy from 40 % of its width.
* ui/dashboard.py: setup buttons map section pages (listening) to their parent page (SECTION_OF).
* personality/flavour.py: tone asides draw from the neighbouring levels too; dialogue.pick remembers all but one line of a pool of 12 or fewer.
* core/updater.py: reuses a staged copy of the same version; mkdir(exist_ok) after a failed delete (WinError 183).
* tts/kokoro_tts.py: British voices (bf_/bm_, their own lang_code "b" engine, made on first use) and am_santa added to the voice list.

## 0.78.0 - Streaming, stage one (Twitch)

* streaming/chat.py: the rules (parse, who may use it, blocked words, cooldowns, the fixed ACTIONS list, action_blocker safety checks). ChatDirector calls only three functions that touch the outside: do_action (runs the action's phrase through the normal voice-command runner, so only the player's own keys are pressed), do_ask, say.
* streaming/twitch.py: read-only anonymous IRC (justinfan, no token), parse_line / message_from (moderator and subscriber badges), reconnect with back-off. Nothing is ever sent except JOIN, PONG and the log-in lines.
* streaming/bridge.py: supervisor thread (follows the settings every 3 s) + worker thread with a small queue (floods are dropped) + pretend() for the dashboard test box.
* streaming/wiring.py: builds the bridge from the app; make_chat_brain() is a second Brain with no profile, people, unanswered list or follow-up prompts.
* streaming/voice.py: 'pause the chat' / 'chat on'.
* Settings: the streaming.* section (core/settings.py), page in ui/settings_model.py, status + test box in ui/dashboard.py (_build_streaming).
* Not tried against live Twitch: the first real connection will show any problems in the log.

## 0.79.0 - YouTube chat, exobiology rule check, logo

* streaming/youtube.py: read-only YouTube Data API v3 live chat. video_id() takes a link or id, parse_messages() keeps text messages only (owner/moderator/member flags from the API), YouTubeChat finds activeLiveChatId, skips the backlog on first fetch, polls at the speed Google asks but never faster than every 10 s (quota: 5 units a call, 10,000 a day), and handles quota/key/ended-chat problems with plain status text. The key is never put in a status or log line.
* streaming/bridge.py: now keeps one slot per platform, so Twitch and YouTube can run together; status shows both when both are on. Settings: streaming.youtube_key, streaming.youtube_video (page fields in ui/settings_model.py).
* config/bio_rules.json: High Metal Content added to Fungoida Stabitis/Gelata, Osseus Discus/Pellebantus, Tussock Ignis/Serrati/Pennatis; argonrich added to Osseus Pumice. Checked against ~1,000 real scanned life bodies from tester journals: species recall about 98.8% -> 99.8%, candidate genera per body about 4.6 -> 4.65. No personal data from those journals is stored in the repo.
* Website: logo (tools/site_assets, copied to site/ by tools/build_guide.py), YouTube setup steps in the For streamers section.
* Not tried against live YouTube: the first real connection will show any problems in the status line and the log.

## 0.79.1 - Change log on the website, private phrase

* tools/build_guide.py: changelog() builds the "Change log" section from the "New in x.y.z:" notes in README.md (newest 10 open, older ones folded away). nice() tidies the shouted titles.
* control/easter_eggs.py: private phrases that are rewritten into ordinary commands before matching. They are deliberately not in control/catalog.py, so they never show in help, dashboard lists or the website; tests/test_easter_eggs.py checks that. Do not document the phrases anywhere.

## 0.79.2 - Lasting exobiology sales, dying with exobiology on board

* config/mood_rules.json: sell_exo has "lasting": true (personality/mood_engine.py _apply skips the soft cap and the hourly cap for such rules) and new, higher tiers up to 5 billion (2 billion = 75 base points). The old big_bio_sale swing is removed (it also tested a field that biology sales do not have, so it never fired).
* Dying with 10 million or more unsold exobiology: rule died_with_exo (0 points) and swing died_exo (Upset, level 1, 10 minutes, announces itself, forgives at the end). MoodEngine.exo_provider (set in core/app.py) gives the credits carried; the engine remembers the last value because the tracker empties itself on death. The lost-data penalty is skipped in that case so nothing is lost for good.
* Swings can now have "level" and "announce"; lines in voicepacks/default/swings.json (Upset_DiedExo, Forgive_DiedExo, Still_DiedExo).

## 0.79.3 - Website guide box

* ui/dashboard.py _banner_title draws a clickable 'WEBSITE GUIDE' box left of the microphone box (the banner is shared by every page); open_guide() opens ui/status.GUIDE_URL. guide_box(right) in ui/status.py works out where it goes (None when the window is too narrow) and is tested in tests/test_guide_box.py. The drawing and the click are GUI code and were not run in the sandbox.

## 0.79.4 - Route map look

* navigation/galaxy_map.py: background() now returns see-through KEY pixels with orange (#ff8c1a) region borders only; AHEAD cyan, BEHIND dimmer cyan, WAYPOINT yellow, WAYPOINT_DONE dimmer yellow; every text colour is orange. ui/route_overlay.py: the frame is orange with no panel fill (the see-through colour is the canvas background). Colour test in tests/test_route_map.py. The look on screen is untested (GUI).

## 0.79.5 - Route map zoom

* navigation/galaxy_map.py: zoom_view() fits points with a thin margin (EDGE_ROOM 8%), route_view() starts with the whole route and after each passed waypoint begins at that waypoint (plus the remaining waypoints, the destination and your position). The inset (small whole-galaxy picture) and its drawing code were removed. Never zooms past MIN_SPAN_LY (1,500 ly) or beyond the galaxy. Tests in tests/test_route_map.py (RouteZoom). The on-screen result is untested (GUI).

## 0.80.0 - Log fixes

* navigation/edastro.py: the full landmark list (/gec/json/combined) is cached in data/poi_cache.json (refreshed weekly); nearest_local()/nearest_many() find the nearest by distance; navigation/voice.py _nearest_known_place walks that list nearest-first and checks each name on Spansh. EDAstro itself was not reachable from the sandbox, so the download is untested live.
* memory/stats.py: visits now also hold a 'scanned' body count; scan_history(folder) reads old journals once (history_done flag in stats.json) and seed() merges the result; MAX_SYSTEMS 5000 (TRIM_BY 500 oldest dropped); FSDJump into a known system says Stats_Revisit or Stats_Revisit_Scanned (voicepacks/default/stats.json) with a 10 minute cooldown. core/app.py start_stats_history() starts the scan in the background.
* personality/llm.py: looks_foreign() and extra refusal/leak phrases make clean_reply() reject odd replies. streaming/chat.py tidy() strips emoji and emoticons. streaming/bridge.py _youtube_notes() and INFO status logging.
* Dialogue: Curd Nerd removed from callouts.json; about 130 variants added (dialogue.json, talk.json, biodistance.json, routemap.json). Tests: tests/test_session_fixes.py.


## 0.80.1 - Route map fixed view

* navigation/galaxy_map.py route_view() now always fits the whole route (zoom_view of all points); the per-waypoint zoom was removed at the user's request. tests/test_route_map.py updated. Looks on screen untested (GUI).

## 0.80.2 - Snappier

* tts/kokoro_tts.py: sentences_of() splits an uncached line into sentences; each is loaded from or saved to the cache on its own, then the whole line is cached as before. tts/voice_warmer.py: mining_texts() pre-makes Refined_First*/Refined_Cheer/Prospected_Motherlode for favourite and GOOD minerals and Refined_Milestone* for counts every 3/5/10 tonnes up to 20, favourites only (setting tts.warm_mining, default on); it runs after the fixed lines. personality/watcher.py: retry_delay() backs off 10 s up to 120 s while Void Compass is offline. memory/recall.py: spoken_summary() drops a long mission title. navigation/voice.py: a SpanshError mentioning the starting system also starts the emergency protocol. Tests in tests/test_session_fixes.py and tests/test_callouts.py. Real voice speed is untested in the sandbox (no Kokoro).

## 0.80.3 - Warm-up no longer repeats

* Cause (found in the 5 Nov log: '15 made, 5755 already there' at every start): lines over MAX_CACHED_CHARS (200) were never saved, so is_cached() was always False and the warm-up re-rendered them each launch. tts/kokoro_tts.py: _units() splits such text into sentences; render() and is_cached() work on those units, so they are kept and recognised. Test: tests/test_speed.py test_a_very_long_line_is_kept_sentence_by_sentence.

## 0.80.4

* tts/voice_warmer.py mining_texts() trimmed to favourites, Refined_Milestone only, counts up to 20 (about 1,700 lines instead of 4,800).

## 0.80.5 - Prepared once

* tts/voice_warmer.py: _fingerprint() (speed, voice signature, every line) is saved to data/voice_prepared.json when a run ends with no failures; _already_prepared() skips the whole warm-up when it matches and about 40 spread-out lines are really in the cache. kokoro.cache_signature() added. The dashboard button (force) always checks. Test: tests/test_speed.py test_no_second_check_once_fully_prepared.

## 0.80.6 - Route map hides with Void Compass

* personality/watcher.py: last_ok and void_compass_running() (Void Compass answered in the last 45 s). ui/route_overlay.py: wanted_mode(..., void_compass) returns None when running and the setting overlay.route_hide_with_voidcompass (default on) is set; test mode still shows. ui/dashboard.py passes the provider. Tests in tests/test_route_map.py and tests/test_session_fixes.py. Overlay behaviour on screen untested.

## 0.80.7 - Line picker memory and mood log

* personality/dialogue.py: pick() keeps per-key recent TEXTS, a global deque of the last 40 spoken texts (GLOBAL_MEMORY) and avoids repeating a global recent text or an opener (first two words) from the last 5 (OPENER_MEMORY), always falling back when it would leave nothing. attach_memory()/save_memory() keep it in data/recent_lines.json (saved every 25 picks and on stop). personality/mood_engine.py: _apply() logs changes of 1 point or more at INFO. Tests in tests/test_session_fixes.py.

## 0.80.8 - Voice start and helper registry

* tts/kokoro_tts.py: model_is_downloaded() and HF_HUB_OFFLINE=1 (cloned voice only, model already in the Hugging Face cache); loading_seconds(); 'Kokoro voice ready' now logs the time split (engine / voice file / first sentence). ui/status.py shows the seconds. control/runner.py: voice_helpers() (named, ordered: extra helpers, small talk, memory, route) and add_helper(helper, first=False); a debug line names the helper that answered. Tests in tests/test_session_fixes.py. The real load time effect is untested (no Kokoro in the sandbox); the new log line will show it.

## 0.80.9 - Window position

* ui/window_memory.py: parse_geometry/usable_geometry (pure, tested) and WindowMemory (tkinter): restore() before showing, save() on close; settings window.geometry and window.maximised. The desktop area comes from Windows GetSystemMetrics (virtual screen, can start negative with a left-hand monitor). Real multi-monitor behaviour untested (no screen in the sandbox).

## 0.81.0 - Safety nets

* core/diagnostics.py (make_bundle, redact; button on Updates and Developer pages). core/backup.py: backup_if_new_version() runs first in app.start (data/ to data_backups/<old version>-<date>, newest 3 kept, SKIP caches) and run_migrations() with the MIGRATIONS list and data/data_format.json (format number; none yet). data_backups added to the updater KEEP list. tools/check_dialogue.py + tests/test_content_check.py. The update rollback that already existed (core/updater.py, .previous folder and start-up test) is unchanged. Buttons and desktop zip untested live (GUI).

## 0.81.1 - Settings check

* core/settings.py: check_settings(values, defaults) (_fit converts or resets by the default's kind; difflib typo hints inside known groups), run by Settings.load(); problems kept in Settings.problems and logged as warnings. Text settings are left alone on purpose. Tests in tests/test_content_check.py.

## 0.81.2 - Timing

* core/timing.py JobTimer: per-job counts/totals/longest, 10-minute summary with process CPU time, 'Slow job' lines over 0.5 s (once a minute per job). core/event_bus.py times every listener (EventBus.timer); core/app.py stop() writes a final report. Tests in tests/test_content_check.py.

## 0.85.9 - Woz log fixes

* sender.WindowsWindows: argtypes for 64-bit handles, find_game tolerant; keys.py Hash; binds/combat_assist warn once; timing.thread_cpu_times + busiest_threads in the 10-minute line.

## 0.85.10 - Updates while running

* update_service: repeating background check (30 min), stop(), restart_now(); launcher passes STARLING_LAUNCHER_EXE; dashboard title note + Restart button.

## 0.85.11 - Held chat questions

* streaming/chat.py ChatDirector: quiet_provider, held deque (cap streaming.hold_max 4, hold_max_age 300 s), pump(); bridge worker pumps each second; wiring.quiet() = speech idle + 4 s silence + no combat/danger/jump/charging.

## 0.85.12 - Website: UI Down rule

* guide_template.html: UI Panel Down rule, role panel key row.

## 0.86.0 - Sub targeting

* control/subsystems.py (names), game_state target_* fields filled by combat_events._target_update, macro step `subsystem <key>`, runner._subsystem_step (press CycleNextSubsystem, wait for ShipTargeted, up to 14), commands sub_powerplant/engines/fsd/shields/lifesupport/distributor/sensors/cargo, statuses no_target/no_scan/no_subsystem/sub_unread with voice pools.

## 0.86.1 - Left panel tabs

* catalog: panel_navigation / panel_transactions / panel_contacts / panel_target = LEFT_TAB (open left panel + tab N); left_panel phrases narrowed to 'left panel'.

## 0.86.2 - Sub target fixes

* subsystems.py: engines = ext_drive, cargo = modularcargobaydoor, weapons = hpt; runner._subsystem_step ignores an adjacent repeat, 24 presses; sub_weapons command.

## 0.86.3 - Faster sub targeting

* journal/monitor.py look_fast(seconds); runner.journal_boost (set in core/app.py) wraps _subsystem_step: boost(40) ... boost(0) in finally; 0.05 s waits.

## 0.86.4 - Shorter way round, yes + command

* subsystems.RING / which / shorter_way; runner._subsystem_walk picks Next or Previous; confirm.py accepts 'yes, <the command>' and a 15 s window.

## 0.87.0 - Red alert

* core/red_alert.py (switch + voice helper), SpeechManager.alert drops low-priority chatter, Flavour.red_alert skips remarks/pet names, KokoroTTS.speed_boost, ui/red_alert_overlay.py (two click-through windows: pulsing frame + tint), settings red_alert.*, Red alert page, voicepack RedAlert_On / RedAlert_Off.

## 0.87.1 - Red alert calmer + combat mode

* red_alert_overlay: steady (no pulse), thinner edge, stronger tint; RedAlert(combat_mode=app._red_alert_combat_mode) runs 'switch to combat mode' in a thread; setting red_alert.combat_mode.

## 0.87.2 - Red alert focus + speed

* red_alert_overlay: windows created withdrawn, _harden (layered/transparent/toolwindow/noactivate) re-applied on every show, ShowWindow SW_SHOWNOACTIVATE + SetWindowPos NOACTIVATE; default speed 1.2.

## 0.88.0 - Red alert banner

* red_alert_overlay.py rewritten: one transparent click-through window with RED ALERT text at the bottom centre; filter/glow/tint settings removed; settings red_alert.banner / red_alert.size.

## 0.88.1 - Red alert: no speed-up, banner like the bio box, quiet in combat

* red_alert.speed removed (uncached fast speech cost up to 120% of a core). ui/red_alert_overlay.py now a canvas window like bio_overlay. Flavour(combat_provider) -> app._in_combat (target_locked or attacked_at < 120 s) drops pet names and remarks.

## 0.88.2 - YouTube chat: growing back-off on 403

* streaming/youtube.py _api_problem: unknown errors (403 forbidden) wait 30/60/120/240/300 s, reset by a good fetch; clearer status text.

## 0.88.3 - Sub targeting presses ahead

* GameState.target_history (last 80 ShipTargeted lines). runner._subsystem_press_ahead: after SLOW_PRESSES=3 careful presses, taps every ~0.18 s, reads answers from the history, stops at the first match, steps back over the extra presses with the opposite key, falls back to careful steps; setting subtarget.press_ahead. Tests: tests/test_subtarget.PressAhead (fake game with 0.55 s lag).

## 0.88.4 - Chord letters clash

* BindingBook.conflicts also reports a chord's non-Shift/Ctrl/Alt modifier keys that are bound on their own to another action in the same view (night vision S+V+R+RShift vs DeployHeatSink on V).

## 0.89.0 - Noticing, looking back, calm combat lines

* personality/chitchat.py: counters (kills, interdictions, scans, systems, since_scoop), MILESTONES + milestone_keys() (first in the pick order), last_moment callbacks (ChitChat_Callback_*), setting chitchat.notice. voicepacks/default/chitchat.json: new pools. Tests: tests/test_chitchat.Noticing, LookingBack.

## 0.89.1 - docs/TODO.md

* The running done / to-do list lives in docs/TODO.md. Update it with every version.

## 0.89.2 - Teach, reactions, welcome back, utility sub targets, thread owners

* control/teach.py (TeachHelper: 'I meant ...', 'what did you miss'), learning.misses/teach; speaker._with_reaction + voicepacks/default/openers.json (rng must be passed in, tests leave it off); streaming/wiring.asks_key + ChatDirector.asked; subsystems.UTILITY keys + catalog sub_chaff etc.; timing.thread_owner (Windows).

## 0.89.3 - Optional Australian voice (MeloTTS)

* tts/melo_voice.py (MeloEngine, resample 44100 -> 24000, is_installed); KokoroTTS._engine returns it for the voice name melo_en_au (BUILT_IN_VOICES); falls back to the cloned voice with one log line when MeloTTS is missing. tests/test_melo.py uses a fake model.

## 0.89.4 - run_try_australian_voice.bat

* Private-folder MeloTTS try-out (tools/try_melo.py). MeloTTS stays out of requirements.txt (the launcher installs that for everyone; MeloTTS pins old versions).

## 0.89.5 - try-out v2

* First try (Windows, Python 3.12) failed on fugashi (needs C++ Build Tools) and tokenizers (needs Rust) pinned by MeloTTS (transformers==4.27.4, fugashi==1.3.0). Now --no-deps plus modern add-ons.

## 0.89.6 - try-out measures speed and memory

* 0.89.5 worked on Windows (Python 3.12, modern add-ons, --no-deps for MeloTTS). First sentence 16 s, load 50 s. tools/try_melo.py now times four sentences and prints memory.

## 0.89.7 - Australian voice one-click install

* Voice page button installs MeloTTS in data/melo_env; runs as a separate worker (tts/melo_worker.py) with idle shutdown; warm-up limited to 400 lines for this voice.

## 0.89.8 - updater moves her files instead of copying

* core/updater.py: _copy_keep moves (instant) with restore on failure/rollback.

## 0.89.9 - next weapon, disk-space safeguards, last-session recap

* control/runner.py _next_weapon; tts/voice_space.py + Voice page clear button; melo_install free-space check; memory/stats.py recap + greeter Login_Recap.

## 0.90.0 - settlement maps (first step) and recorder

* navigation/settlement_maps.py, ui/settlement_overlay.py, control/settlement_voice.py, maps/settlements/; navigation/settlement_recorder.py; heading/altitude kept from Status.json; journal processor raw_listeners.

## 0.90.1 - no auto pips for the scanners

* control/combat_assist.py fighting(): analysis mode (hardpoints in) only counts while mining_until is in the future, so the Discovery and Composition scanners get no pips; tests/test_combat_assist.py.

## 0.90.2 - Australian voice install fix

* tts/melo_install.py online_env() strips HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE for the install and the worker (tts/melo_voice.py); tests/test_melo.py.

## 0.90.3 - two commands from a tester's log

* control/catalog.py fss_enter off phrases; control/bio_voice.py short hide/show forms; tests/test_stage6.py, tests/test_bio_overlay.py.

## 0.90.4 - fixes from a stream log

* control/sender.py find_game and ui/screens.py use a private WinDLL('user32').EnumWindows (the shared one had its argtypes changed by the other); personality/smalltalk.py greeting + how-are-you, slang hellos, chat/everyone filler; control/catalog.py hide-all-overlays mishearings and bare 'hardpoints'; streaming/bridge.py logs the YouTube wait once; tests/test_talk.py.

## 0.90.5 - she feels more alive

* control/runner.py `_unmatched` + `_chat_jobs` (one worker thread, `background_chat`, set in core/app.py); journal/game_state.py `notable` filled by events/scan.py; config/brain_intents.json `system_finds` + personality/brain.py `_system_finds`; brain `_ASK_PET` wider and honest; personality/manners.py `THANKS_FOR`; personality/llm.py helpdesk LEAKS; tests in test_commands, test_brain, test_profile_confirm, test_manners, test_llm.

## 0.91.0 - red alert picks the power plant

* control/auto_subtarget.py `AutoSubTarget` (a journal raw listener, started in core/app.py): ShipTargeted with ScanStage 3 and no Subsystem, red alert active, not supercruise/docked/on foot, once per ship, runs 'target power plant' with auto=True; setting red_alert.auto_power_plant (ui/settings_model.py); tests/test_auto_subtarget.py.

## 0.92.0 - settlement maps: all 28 layouts, rotation finder, auto show/hide, north-up map, voice arrow

* maps/settlements/*.json: 28 layouts (tourist 1-4, agriculture 1-5, military 1-5, industrial 1-5, extraction 1-5, high tech 1-4), traced by eye from CMDR Quizengine's Odyssey Map Guide.
* navigation/settlement_solve.py: tries every turn (3 degree steps) and three scales around 0.325 m per map unit for the spots you stood at (terminals, doors, power, alarm; the ship's pad is left out, it is only roughly placed), keeps the best of each different turn, tightens it with a least squares fit, and says yes only if the average miss is small and the next different turn is clearly worse (`clear`). Several candidate layouts are compared the same way.
* navigation/settlement_track.py: `SettlementTracker` collects `spots` (voice marks, plus a terminal screen opening on foot = Status GuiFocus 5, a guess), calls the solver, saves the result per MarketID; shows the map on foot within 700 m and hides it when you embark or leave; `dismissed` after 'hide the settlement map'; sets `MapView.turn` (north up) and `MapView.target`; voice 'find / where is / nearest' + terminal, power plant, alarm, airlock, door, ship; 'stop pointing'.
* navigation/settlement_maps.py: `projector` / `layout(..., turn)` turn the drawing so north is up; ui/settlement_overlay.py draws the north-up map, your arrow (your heading) and a dashed arrow with a ring at the target.
* navigation/settlement_recorder.py: trail rows now hold the GuiFocus number as the 5th value, to confirm what the terminal screen number is.
* tests/test_settlement_solve.py, tests/test_settlement_track.py (terminals only, auto show/hide, hiding by voice, the pointer).
* Not tested in the real game: overlay, arrow, terminal-screen mark, pad counts for 26 of 28 maps.

## 0.92.1 - settlement tracker reads the caught-up journal

* navigation/settlement_track.py `on_entry` no longer drops `silent` (catch-up) lines, so ApproachSettlement/DockingRequested/Docked seen before Starling started still set the settlement; the ship's pad position is only taken from live lines. Found in diagnostics 20261110-143023 (Starling started after the approach, no map). tests/test_settlement_track.py `StartedLate`.

## 0.92.2 - 'show settlement map' lists the layouts it could be

* control/settlement_voice.py `options`; navigation/settlement_track.py `options()` and `set_dismissed(False)` makes a named map the settlement's map. Found in diagnostics 20261110-144526 (Cheesebeard's Cave: Extraction, Large 1, four layouts share it). tests `WhenSheCannotChoose`.

## 0.92.3 - spoken settlement answers, known settlements list

* control/runner.py finishes helper answers with speak=False, so helpers must speak for themselves: SettlementMapVoice and SettlementTracker get a `say` callback (core/app.py, speech.say). Asks once on foot when several layouts match.
* maps/known_settlements.json (MarketID -> map id, loaded by settlement_track.known_settlements): Shi Construction = industrial_2. Found in diagnostics 20261110-152207. tests `KnownSettlements`.

## 0.92.4 - Shi Construction ships lined up

* maps/known_calibrations.json (MarketID -> Calibration JSON, from the power/alarm/pad fit, rms 2.2 m) loaded as `shipped` in navigation/settlement_track.py; recorder keeps `focus` changes on foot (visit['focus']). Found in diagnostics 20261110-155722. tests `ShippedLineUp`.

## 0.92.5 - recorder resumes after a restart, lists events

* navigation/settlement_recorder.py: silent (catch-up) ApproachSettlement resumes the unended visit with the same MarketID instead of starting a copy; silent SupercruiseEntry/FSDJump/Shutdown end it; `visit['events']` lists other journal events (QUIET_EVENTS skipped, 300 max). navigation/settlement_track.py logs on-foot GuiFocus changes near a settlement. Found in diagnostics 20261110-155722 (no terminal data). tests `AfterARestart`.

## 0.92.6 - standing still on foot = a stop

* Diagnostics 20261110-173027 (0.92.5): no journal event and no GuiFocus (not in the on-foot Status fields) when a terminal is used, so the GuiFocus guess is removed. Trails show 6-10 s stationary stretches exactly at terminals. navigation/settlement_track.py `_dwell` (DWELL_SECONDS 6, STILL_METRES 2.5, GOT_OUT_METRES 15) adds a 'stop' spot (matches terminal, power regulator or alarm in navigation/settlement_solve.py `features`) and calls `_line_up`. tests `WithoutPowerOrAlarm` dwell tests.

## 0.92.7 - a stricter line-up

* Diagnostics 20261110-183217: extraction_3 lined up from 3 stops (miss 1 unit, scale 0.276) and was wrong. Simulation (spots sampled from one layout, solved against another): false accepts 15/120 with 3 spots, 3/120 with 4, 0/120 with 5 and 6. navigation/settlement_solve.py: `_cost` matches each feature to one spot only; `clear` needs scale 0.295-0.355; MIN_SPOTS 4, SPOTS_TO_CHOOSE 5 (used when no layout is chosen yet). Calibration JSON carries `v: 2`; saved line-ups without it are ignored (navigation/settlement_track.py). Tests updated.

## 0.92.8 - no press ahead, no Danger warning

* Diagnostics 20261110-220020: every `_subsystem_press_ahead` run read 1 answer for 27 presses (the game drops quick presses) and ended in 'fast-fixed' or 'none'. `subtarget.press_ahead` default is now False (core/settings.py, config/settings.json, control/runner.py); the slow loop retries the first press once. tests/test_subtarget.py PressAhead tests switch it on explicitly.
* config/events.json InDanger: enabled false, priority normal (critical events cannot be switched off); events/in_danger.py priority NORMAL; tests/helpers.py turns it on for the reader tests; tests `DangerIsOffByDefault`.

## 0.92.9 - more hello / goodbye to chat

* voicepacks/default/brain.json: Brain_StreamHello 5->21 (+ Sarcastic, Close, Friendly), Brain_StreamBye 3->17 (+ Sarcastic, Close, new Friendly). Mature lines are flagged as before.

## 0.95.3 - the landing rule checked on three more visits

- Trigger: Benny's zip 20261111-224857 (Peng Synthetics Foundry x2, Makubuya Engineering Silo, both Industrial, 1 large pad).
- Stops (east, north metres from the reference point): Peng (-19,-128), (82,-24), (72,36); Makubuya (130,3), (10,84), (-47,64). Distances 129/130, 85, 81/79 match; bearings differ by -99.7 degrees for all three pairs. Ship heading on pad 1: Peng 172 to 181, Makubuya 74: difference -102 to -107. So the rule holds to about 3 degrees and the two settlements share a layout.
- Same as Shi: Shi's terminals are 130, 79 and 86 m from its reference point; two of three bearings differ from Peng's by -77 (heading says -80). The free solver could not name Industrial 2 or 5 for Peng (average miss 35 to 40 map units for 2, 5 and 3 alike): the guide maps' terminal positions are traced by eye, so a free fit from 3 stops has little to hold on to.
- maps/known_settlements.json: Peng (4367086339) and Makubuya (4358173443) -> industrial_2. Judged very likely, not certain (Industrial 5 is the other one-large-pad Industrial).
- maps/map_frames.json: industrial_2 origin (1075, 416), offset 5 (was 1069, 432, 8.7 from Shi alone). A grid search over the three visits preferred (1080, 400, 1); this is a compromise with Shi. With it the nine stops miss a terminal by 13 to 50 map units, average about 30.
- navigation/settlement_track.py: `DOCK_TRUST_UNITS` 50: `_check_stop` uses it for a `how: dock` line-up (the heading wobble makes it looser than a line-up from stops, 30).
- tests/test_settlement_track.py `SameLayoutDifferentSettlements`.
- Open: still no real-game check that the landing line-up appears and confirms.

## 0.95.2 - the landing lines up the map

- Source of the idea: SrvSurvey (GPL v3; we read how it works but copied none of its files). It works from the pad: pad 1 faces the settlement's heading, other pads add a fixed rotation per layout, and the layout origin is the ApproachSettlement latitude/longitude.
- Check on real data: Shin Prospecting Platform (Extraction 3) first on-foot point, rotated by the ship's Docked heading (151) into the layout frame, came out at (134.7, -54.4) m; the Extraction 3 pad in SrvSurvey's template is (140.4, -52.6). Cheesebeard's Cave (same layout) came out 22 m away (its heading wobbles 212 to 223). The opposite rotation sign put the two 255 m apart, so the sign is right. Shi: the map's calibrated turn plus the ship's heading is 8.7 degrees (3 to 17 over six visits), and the calibrated reference point is 38 map units from where the pad predicts.
- navigation/settlement_track.py: `known_frames()` / `frame_problem()` / `frame_calibration()`; `maps/map_frames.json` (shipped: industrial_2, origin 1069,432, offset 8.7, scale 0.325). `SettlementTracker.frames` = shipped plus learned (`<calibration file>.frames`). `on_entry` keeps `pad_number` from DockingGranted; `_ship_landed` keeps `dock_heading` and calls `_dock_line_up` (pad 1 only, map already known, frame known, not rejected this visit): a = 0.325 * e^(i(offset - heading)), t = -a * origin. The calibration has `how: dock`, is provisional and uses the same check/take-back as the three-stop line-up. A confirmed dock line-up is saved. `_take_back` sets `dock_rejected` so a second touchdown does not guess again. `_remember_frame` learns origin/offset/scale from every non-dock line-up made on pad 1 (running average, at most 9 earlier ones count).
- Pad counts: ten maps changed to SrvSurvey's pad sizes (Agriculture 3 and 5, Extraction 1, Industrial 3 and 5, Military 1, 3, 4, 5, Tourist 2); the other 18 already agreed. Real journals agree for Industrial 2 (1 large), Agriculture 4 (2 small 1 large) and one large Extraction pad at Cheesebeard's and Shin (so Extraction 3). The test table in tests/test_settlement_maps.py is updated.
- Crouch: Status.json Flags (2097157) and Flags2 (33041) are identical standing and crouched (Benny's test, 2026-11-11). Dead end. Temperature changed 10 K over 144 m of walking: not used.
- Not built: pad numbers other than 1 (needs each layout's pad rotation), maps without a pad circle (extraction_3, high_tech_2, tourist_4 have no frame until one line-up is made), using the pad position as an extra anchor for the solver (the Docked position is up to 150 m off because the game gives the cockpit position, not the pad centre).
- Open: the frame of every layout except Industrial 2 is learned from line-ups, so it only helps at the second settlement of a layout. Send zips so we can ship more frames.

## 0.95.1 - three stops are enough

- Trigger: Benny's zip 20261111-190558 (Sharma Hydroponics Farm, Agriculture 4). Recognised from the pads (matches the 2S 1L in the table), but only three terminal stops (the pad does not count, and two stops were suit recharges that are not on the map), so the 4-stop rule gave no line-up.
- navigation/settlement_solve.py: `solve(..., scales=LOCKED_SCALES)` fixes the map size at 0.325 m per unit (turn and shift only); the refine keeps the size. `clear(result, scale_range, good, margin)`. `MIN_SPOTS_LOCKED` 3 (layout known), `SPOTS_TO_CHOOSE_LOCKED` 4 (choosing). The old wide search (4 / 5 stops) still runs second.
- Evidence for one common size: Shi 0.3249; a free fit of the Sharma stops that best matched Agriculture 4 gave 0.329 (only 3 of 7 stops matched, so weak evidence). NOT proven. Needs more real settlements.
- Check made: random walks (jitter 8 units per axis, 0 to 2 junk stops) over all 28 layouts. Fixed size, 3 stops: 99 right, 2 wrong, 39 unsure out of 140. Wide search, 4 stops: 116 right, 4 wrong, 20 unsure. One junk stop with 3 true stops mostly stays unsure; 4 true stops plus 1 junk: 64 right, 1 wrong, 75 unsure. tests/test_settlement_solve.py `LockedSize` repeats a smaller version (87 sure, 4 wrong with 6 units of jitter: about 5 in 100 wrong, which is why a 3-stop line-up is only provisional).
- navigation/settlement_track.py: a line-up from 3 stops is `provisional`; `_check_stop` counts later dwell stops (within `TRUST_UNITS` 30 map units of a terminal, power or alarm = fit). 2 fits confirm; 2 misses and more misses than fits `_take_back` (forgets the saved line-up, says so). Loaded saved 3-stop line-ups are provisional again.
- navigation/settlement_recorder.py: trail rows now carry `status_flags2` and `status_flags` (items 6 and 7) so we can look for flags that change when walking in or out of buildings.
- Idea not built: using those flags (or the walking trail through doors and airlocks) to line the map up without any terminals. Needs a zip with the flags first.

## 0.95.0 - she notices you (habits, rapport, the world, push-to-talk interrupt)

- memory/habits.py `HabitKeeper` (data/habits.json): stations (count + recent days), deaths per system, days played, told steps. Remarks: `Habit_Station_Week` (3/5/8/12 landings in 7 days), `Habit_Station_Home` (10/25/50/100 ever), `Habit_Death_Place` (2nd death or more in a system, said at Resurrect/Location/FSDJump/Docked), `Habit_Streak` (3/7/14/30/60/100 days, said at the next Docked or FSDJump after LoadGame), `Habit_Jumps`, `Rapport_Hours`. One remark per 20 minutes; milestones ignore the gap. First run marks passed milestones as told.
- `rapport(hours)`: new, crew (25h), friend (100h), family (1000h). `core/app.py hours_together()` = saved hours plus this session.
- personality/chitchat.py: new pools `ChitChat_Late` (00:00 to 04:59 on your clock, after 20 minutes), `ChitChat_Early` (05:00 to 07:59), `ChitChat_World` (security, allegiance, population), `ChitChat_Habits` (fav_station, fav_count, days_in_row), `ChitChat_Rapport_Crew/Friend/Family`. Each at most once per 20 minutes; never in combat mode. New line values: clock, weekday, security, allegiance, population, fav_station, fav_count, days_in_row, rapport. `ChitChat(..., wall=datetime.now)` so tests can set the time.
- control/ptt.py: `PushToTalk(..., on_open=)`; the app passes `speech.interrupt()`. Setting `speech.ptt_interrupts` (default on). Safety warnings are never cut off (SpeechManager.interrupt).
- Settings: `memory.habits`, `chitchat.world`, `speech.ptt_interrupts`.
- Lines: voicepacks/default/habits.json, chitchat.json (new keys).
- Already existed (not rebuilt): quiet-time remarks, session milestones and callbacks, 'we've been here before', recap of last session, varied sentence openings, quieter chatter in combat.
- Not built, and why: voice interrupt (she is deaf while talking so she doesn't hear herself, no echo cancellation), a reply delay (adds latency for little gain), asking you things and keeping your answers (needs the answer listener; later).
- tests/test_habits.py.

## 0.94.0 - chat awareness

- streaming/events.py: `StreamEvent(kind, user, amount, platform)`; `from_twitch(parsed)` reads USERNOTICE lines (msg-id sub, resub, subgift, anonsubgift, submysterygift, raid, viewermilestone/watch-streak), `from_youtube(item)` reads superChatEvent, superStickerEvent, newSponsorEvent, memberMilestoneChatEvent, membershipGiftingEvent. Names go through `clean`, numbers through `whole` (0 to 100000).
- streaming/twitch.py and youtube.py hand events to the same `on_message` callback as chat messages; streaming/bridge.py sends a StreamEvent to `director.react` and a ChatMessage to `director.handle`.
- streaming/chat.py `ChatDirector.react / pump_events`: waits for `quiet_provider`, one line per kind per gap (sub 8 s, gift 20 s, raid 60 s, chat milestones 120 s), drops news older than 3 to 10 minutes, keeps at most 6 waiting, collapses the single gift lines that follow a big gift. `_count_chat` counts messages and different people for the chat milestones.
- Lines: voicepacks/default/streaming.json `StreamEvent_Sub / Resub / Gift / Raid / Streak / Tip / ChatMessages / ChatPeople`, with `_Big` (gift 10+, raid 50+), `_Long` (resub 12+ months) and mood sets (`_Sarcastic`, `_Close`, `_Friendly`).
- Settings: `streaming.react`, `streaming.react_milestones` (both default on).
- Honest limits: untested on a live stream. Twitch's anonymous reader should receive USERNOTICE lines, but that is the first thing to check. Twitch "follows" are not in chat, so she cannot react to those without a login (later). Counts are for this session only.
- tests/test_stream_events.py.

## 0.93.2 - voice tuning with inno-kokoro 0.4.0

- Tester report: `Tuner.__init__() missing 1 required keyword-only argument: 'backend'`, then "No voice is available". Cause: inno-kokoro 0.4.0 (10 Nov 2026) made `backend` required, moved torch to the `[torch]` extra and made `enroll()` return NumPy unless `return_pt=True`.
- tts/kokoro_voice_setup.py `enroll_with_inno_kokoro` (the only place that talks to the library) now uses `Tuner(backend="torch")` and `enroll(..., return_pt=True)`; falls back to the old no-argument call if the library is older.
- Test: tests/test_kokoro.py `InnoKokoroVersions`. Real library untested (no network access to install it here).
- Fix on the tester's side: update Starling, restart; the tuning runs once and saves custom_covas.pt.

## 0.93.1 - pad counts for the 28 layouts

- The `pads` field of every maps/settlements/*.json now holds the counts Benny read from the Odyssey Map Guide pictures. They are best guesses, except Industrial 2 and Tourist 1 (real LandingPads). 18 files changed.
- tests/test_settlement_maps.py `AllTheLayouts.PADS` holds the same table; if you fix a map file, fix the table too.
- Pads still shared: Tourist (none), Agriculture 3/5 (1L), Military 1/4 (1L), Industrial 2/3 (1L), Extraction 1/3 (1L), Agriculture 1 / Military 3,5 / Industrial 4 / Extraction 2 / High Tech 1 (1S 1L), Agriculture 2 / Industrial 1 / Extraction 5 / High Tech 2, 3 (1S), Industrial 5 / Extraction 4 (1M). When several match she lists them and you pick, or the stops solver picks (5 stops).
- Cheesebeard's Cave (Extraction, 1 large) is now Extraction 1 or 3 only.

## 0.93.0 - shared settlement line-ups

* navigation/settlement_share.py: `problem` (sanity check of one line-up: v 2, believable size 0.27-0.38 m/unit, real map, sane numbers), `merge` (adds good ones; replaces only a better-proved one that agrees within 12 degrees; reports CONFLICT otherwise).
* navigation/settlement_track.py: `Calibration.meta` (name, n, err, how) saved in data/settlement_calibration.json; `known_calibrations()` loads only entries that pass `problem`; reset by voice stores `{"v": 2, "disabled": true}` so the shipped line-up is not applied again at that settlement.
* core/diagnostics.py includes settlement_calibration.json in the zip.
* tools/merge_calibrations.py zip-or-json ... [--dry-run] rewrites maps/known_calibrations.json. Maintainer steps: collect testers' diagnostics zips, run the tool, read the report, run the tests, bump the version, push.
* maps/known_calibrations.json now carries v/name/n/err/how for Shi Construction (it had no v and would have been rejected by the new check).
* tests/test_settlement_share.py.

