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
