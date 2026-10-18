# Phase 2: STARLING's Ears (the journal reader)

STARLING can now watch Elite Dangerous and notice what happens.
She cannot speak yet (that is Phase 3). For now she prints what she notices.

## Test 1: the demo (no game needed)
Double-click **run_demo.bat**. A pretend play session replays, and you will see
lines like:

    [19:04:13]    normal   FSDJump            Jumped to Alpha Centauri (4.4 ly)
    [19:04:15] !! CRITICAL HullDamage         Hull integrity at 62%

Anything marked `!! CRITICAL` is a safety warning. At the end you should see
`Fuel is low: 6.4 t (20%)` and `Demo finished.`

## Test 2: watching the real game
1. Double-click **run_starling.bat**.
2. It should say `Watching: C:\Users\...\Saved Games\Frontier Developments\Elite Dangerous`.
3. Start Elite Dangerous and play. Undock, jump, scoop fuel, scan something.
   Each event appears in the window within about a second.
4. Press **Ctrl+C** in the window to stop her.

Things to know:
- When STARLING starts she quietly reads today's journal to learn your name, ship
  and location. She does NOT replay old events.
- If Status.json looks like it is left over from an old session (older than
  a minute), she won't announce an old low-fuel flag.

## If she can't find the journal folder
Open `config\settings.json` in Notepad and put the folder path in the
"folder" line, using double backslashes, for example:

    "journal": {
      "folder": "D:\\Games\\Saved Games\\Frontier Developments\\Elite Dangerous",
      "poll_seconds": 1.0
    }

## Where events are saved
Every event is also saved to STARLING's database (`event_log`) so she can look
back on it later. Entries older than 30 days are removed automatically.

## Safety events (always on)
LowFuel, Overheating, InDanger, UnderAttack, Interdicted, HullDamage,
ShieldState, MissionFailed and Died. Editing `config\events.json` cannot turn
these off or lower their priority.

## Adding a new event later
See the comment at the top of `events\__init__.py`.

---

# Update 0.2.1: all the events

STARLING now notices far more:

**Ship controls (from Status.json):** landing gear, hardpoints, flight assist,
lights, cargo scoop, silent running, night vision, mass lock, FSD cooldown,
analysis/combat mode, wing joined/left, and SRV controls (handbrake, turret,
drive assist, high beam).

**Screens:** galaxy map, system map, system scanner (FSS), surface scanner,
codex, comms panel, left/right/role panels, station services, orrery, and
"closed" when you leave a screen.

**Vehicles:** switching between ship, fighter, SRV and on foot.

**On foot:** low oxygen, low health, cold/hot warnings.

**Many more journal events:** touchdown, liftoff, docking granted/denied,
refuel, repair, heat warning and damage, cockpit breach, jet cone boost,
fighter and SRV launches, exploration data sales, codex entries, being
scanned, crimes, combat bonds, vouchers, cargo, mining and more.

Safety events (marked `!! CRITICAL`) can never be switched off.

## Turning noisy events off
Open `config\events.json` in Notepad. Change `"enabled": true` to
`"enabled": false` for any event that talks too much (for example `LightsOn`).
Critical events ignore this, on purpose.

## "What did I miss?" report
When you press Ctrl+C, STARLING lists the journal events she still ignores and
how often they happened. The full list is saved in `logs\ignored_events.txt`.
Send it to me and we'll decide which to add.

## Not read on purpose
Chat messages and friends lists are not read, for privacy.

## Please tell me if something is wrong
The switch numbers inside Status.json come from Frontier's documentation. I
tested them with pretend data but not with the live game, so if one announces
the wrong thing, tell me which and I'll fix it.
