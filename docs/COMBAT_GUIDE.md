# Combat, wings and ship changes (0.13.0)

## Ship change
When you swap ships at a shipyard she says which one ("Switching to the Python."). Lines: `voicepacks/default/combat.json`, key `ShipyardSwap`.

## Her mood in a fight
- **Dying in combat costs nothing.** If you were under attack, had weapons out, or the game names who killed you (including wing fights), no points are lost.
- **Killing wanted ships raises her mood** more than before: 2 points per bounty, 3 above 250,000 credits, 4 above 2 million. Combat bonds give 2, capital-ship bonds 3, killing another commander 1. She also says a short well-done line.
- Edit any of it in `config/mood_rules.json` (`died_combat`, `bounty`, `kill_bond`, `cap_bond`, `pvp_kill`).

## New things she says
Wing invitation, someone joining, you joining/leaving, a wanted ship you lock onto, interdiction success/failure, commander kills, suit loadout changes, and on-foot lines for being shot at, kills and dying (`*_OnFoot` keys).

## New voice commands (start with "Starling,")
- **Wingmen:** "target wingman 2" (also "wingman two", "lock wing mate 3"), "assist wingman 2" (locks them, then locks what they are shooting at), "wing nav lock"
- **Targets:** next/previous hostile, highest threat, subsystems (already there)
- **Ship:** "charge the ECM", "power to engines / weapons / systems", "reset the pips"
- **Fighter:** "fighter attack my target", "fighter defend", "fighter hold fire", "fighter follow", "recall the fighter", "fighter orders"
- **On foot:** "draw primary weapon", "draw secondary weapon", "holster", "reload", "melee"

These press the key YOU bound in Elite. If one is not bound she tells you which control needs a keyboard key.

## Not tested / limits
- I can't run Elite from here. The on-foot "being shot at" line only fires if the game writes an attack event on foot; if it doesn't, you still get low-health, kills and death lines.
- The game doesn't tell her when a wingman dies, so she can't comment on that.
- The Elite control names for fighter orders and on-foot weapons are from memory of the game's bindings file; use "Check my Elite keys" on the Controls page to see which are missing.

# Small talk (0.14.0)
When it has been quiet she says something small and silly. She only does it when you are in the game, nothing has been spoken for a while, she hasn't chatted recently, and nothing alarming happened in the last minute. Real warnings always win: chatter is the lowest priority and is dropped if she is busy.
- Combat mode: lines about the fight. Analysis mode: exploring. Docked and supercruise have their own. Otherwise general jokes ("clear your browser history...").
- Dashboard > Personality > "Small talk when it is quiet", and "How often she chats" (Rarely about every 25+ min, Normal about every 12 to 20 min, Often about every 6 to 10 min).
- Add your own lines in `voicepacks/default/chitchat.json`.

# More connection (0.15.0)
- **Longer sentences:** jumps, docking, undocking, supercruise, landing, lift-off, fuel scooping, routes and weapons now have fuller, chattier lines (`voicepacks/default/talk.json`). They mix in with the short ones.
- **She talks about your trip:** while flying she may mention your ship, the system, how many jumps and light years you've covered, how long you've been playing, or something she remembers (never during a fight).
- **She chats more:** Normal is now about every 3 to 6 quiet minutes (the new **Chatty** setting is about every 1 to 2). Dashboard > Personality > "How often she chats".
- **Talk to her:** say "Starling, how are you?", "tell me a joke", "talk to me", "I'm bored", "are you there?", "good morning", "good night", "I'm back", "good job", "what's your name?". Kind words give a small mood lift. Switch off with `smalltalk.enabled` in settings.json. Her answers are in `voicepacks/default/smalltalk.json`.

# Her back story (0.16.1)
**The story:** the East Orion Company's R&D department rescued her from a far-off planet of unknown origin (logged as "Planet, Probably"), and gave her to you to test. They didn't build her, and nobody knows who did.

Ask her **"who are you?"**, **"what's your name?"**, **"what are you?"**, **"tell me about yourself"**, **"who made you?"**, **"tell me about the East Orion Company"**, then **"tell me more"** for the next chapter. She tells the chapters in order and never repeats one until she has run out.
- **Calm:** the company brochure version (4 chapters).
- **Friendly:** she also tells the real story: the planet, the vault, how she was found (5 more).
- **Close:** she also tells the personal chapters (3 more).
- **Bad mood (Sarcastic or Frustrated):** the horrible things that happened to her, as dark comedy (9 chapters). Ask while she is cross.
- If she has told all she is allowed to, she says there is more if you are kind to her.
- Heard chapters are saved in `data/lore.json` (delete it to hear them again). Words: `voicepacks/default/lore.json`; add new chapters at the END of a list.
The East Orion Company, the planet and everything about them are invented for her, not Elite Dangerous canon.

# Combat helpers and speed (0.17.0)

## What she says
- **Ship name:** when your hardpoints are out and you lock a ship she says what it is ("Locked on. Cobra Mk III.").
- **Bounty:** when the scan reaches the bounty ("Wanted. 12,500 credit bounty. Shoot it!"). Once per target.
- She really enjoys a fight now, so her combat lines (under attack, kills, weapons, shields, hull, interdiction) are keen and gleeful.
- Words live in `voicepacks/default/combat.json` and `dialogue.json`.

## Automatic helpers (Dashboard > Controls, all on by default)
They only press keys YOU bound in Elite (Elite must be in front, and each action needs a KEYBOARD key as well as any joystick button; she tells you once if one is missing).
- **Pips:** while hardpoints are out, holding a fire button puts 4 pips in weapons (`IncreaseWeaponsPower` x4). About 1.2 s after you let go: `ResetPowerDistribution`, `IncreaseSystemsPower`, `IncreaseEnginesPower`. She reads your Primary/Secondary fire buttons from Elite's controls file (keyboard keys, and X52 buttons 1 to 32). Extra buttons can be listed in settings.json: `combat_assist.fire_buttons` like `"joy:06A3:075C:1, key:F13"`. Change the steps with `combat_assist.pips_firing` and `combat_assist.pips_resting` (lists of Elite action names).
- **Heat sink:** Elite does NOT tell programs ship heat either. The game's overheat warning (about 100%) is the earliest signal, so she fires a heat sink then (8 s gap). Never while docked, landed or scooping fuel.
- None of these has been tested against the real game (no Windows or Elite here). Please field test and tell me what feels wrong.

## Speed
- Saving events to the database no longer holds her up (written in the background).
- **She prepares her voice in the background** while the computer is idle (Dashboard > Voice > "Prepare her voice"). New lines are slower the first time because they have to be made; after that they are instant. After an update, press **Prepare her voice now** (Voice page) or run `run_build_voice_cache.bat` once.
- She stops listening 550 ms after you finish speaking (was 700), and push-to-talk now cuts off her chat when you press the button.
- Slow answers are written to `logs` as "Slow start", "Command ... took" and transcription times, so we can see exactly where time goes.
