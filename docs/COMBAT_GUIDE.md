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
