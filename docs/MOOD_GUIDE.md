# How Starling's mood works

Her mood follows what you do in the game. Choose **Automatic** under *Personality > Mood control* on the dashboard (or **Fixed** to pick her mood yourself). *Info only* style switches the banter off but she still keeps score quietly.

## The mood levels

| Score | Mood |
|---|---|
| 30 and above | **Close** (very happy, fond of you) |
| 10 to 30 | **Friendly** |
| -10 to 10 | **Neutral** (calm and professional; where she settles when nothing is happening) |
| -35 to -10 | **Sarcastic** (annoyed) |
| -35 and below | **Frustrated** |

Scores run from -100 to +100 and start at 0. The score is saved in `data/mood.json`.

## Notoriety (being wanted)

While the game says you are **wanted** (a bounty or notoriety where you are), she loses **6 points for every hour you are actually playing**.
- It only counts for 5 minutes after each game event, so leaving the game running does not drain her.
- She does not calm down, and gets no 'time together' bonus, while you are wanted.
- It stops at **-25** (Sarcastic). Notoriety alone annoys her but never takes her all the way to Frustrated; other actions can.
- It clears when the game says you are no longer wanted (a new system, docking somewhere clean) or when you pay bounties or fines.
- How we know: the journal's `Wanted` flag on Location, FSDJump and Docked, plus any crime that gives you a bounty.

## The brakes (so she never swings wildly)

1. **Soft cap** - doing the same *kind* of thing again counts only 60% as much as the time before. Five repeats are worth about 2.3 times the first, never more than 2.5 times. It recovers after about 10 quiet minutes.
2. **Hourly cap** - her mood can rise by at most 15 points and fall by at most 15 points in any hour (for actions; the notoriety drain is slow on its own).
3. **Calming** - the score drifts back toward 0 by 1 point every 20 minutes (she forgives you), except while you are wanted.
4. **Hysteresis** - she moves UP to a better or worse band the moment she reaches the line (Close at 30, Friendly at 10, Neutral above -10, Sarcastic at -10 or lower, Frustrated at -35 or lower), but only falls BACK once she is 4 points past it (Close until 26, Friendly until 6), so she doesn't flip back and forth. (Before 0.24.3 the 4 points also applied going up, so she needed 34 for Close until you restarted.)
5. **Not nagging** - she says something about an action at most once every 90 seconds, and stops mentioning it when repeats are worth almost nothing.
6. **Safety first** - she never talks over, or instead of, safety warnings.

## Everything that changes her mood

| What you do | Points | Group (soft cap) | Condition |
|---|---|---|---|
| Trading slaves | -4 | illegal_trade | Type is slaves |
| Buying slaves | -4 | illegal_trade | Type is slaves |
| Selling illegal or stolen goods | -2 | illegal_trade | illegal / stolen / black market |
| Buying illegal goods | -2 | illegal_trade | illegal / black market |
| Killing civilians | -6 | violence | CrimeType murder |
| Piracy | -4 | violence | CrimeType piracy |
| Attacking innocent ships | -3 | violence | CrimeType assault |
| Getting a fine or bounty | -2 | crime | any other crime |
| Arriving somewhere you are wanted | -1 | notoriety | the game says you are wanted there |
| Docking somewhere you are wanted | -1 | notoriety | the game says you are wanted there |
| Shields lost outside of combat | -2 | careless | NOT in combat |
| Hull damaged outside of combat | -3 | careless | NOT in combat (your ship, not a fighter) |
| Cooking the ship | -2 | careless |  |
| Jet cone damage | -2 | careless |  |
| Running low on fuel | -1 | careless |  |
| Getting the ship destroyed | -4 | death |  |
| Self-destruct | -3 | death |  |
| Failing a mission | -3 | missions_bad |  |
| Abandoning a mission | -2 | missions_bad |  |
| Selling exobiology data | 100,000+: +1 / 1,000,000+: +2 / 10,000,000+: +3 / 100,000,000+: +4 | sell_exo |  |
| Selling exploration data | 100,000+: +1 / 1,000,000+: +2 / 10,000,000+: +3 / 50,000,000+: +4 | sell_data |  |
| Selling exploration data | 100,000+: +1 / 1,000,000+: +2 / 10,000,000+: +3 / 50,000,000+: +4 | sell_data |  |
| Completing a mission | +2 | missions_good |  |
| Paying off fines | +3 | repent |  |
| Paying off bounties | +3 | repent |  |
| Claiming a bounty | +1 | bounties |  |
| Earning a combat bond | +1 | bounties |  |
| Cashing in vouchers | +1 | bounties |  |
| Escaping an interdiction | +2 | survival |  |
| Rescuing escape pods | +2 | rescue | escape pods / cryo pods |
| First footfall on a species | +3 | discovery | finished sample + first footfall |
| Finishing a biological sample | +1 | exo_samples | finished sample |
| Finding every body in a system | +1 | discovery |  |
| Mapping a body | +1 | discovery |  |
| New codex entry | +1 | codex | new entry only |
| Engineer progress | +1 | engineer | when an engineer actually progresses |
| Time spent together | +1 | time_together | every 25 min of active play (not while wanted) |
| Being wanted (per hour of play) | -6 | - | see Notoriety above |

Only the first matching rule counts for each game event.

## Change it

Everything above is in `config/mood_rules.json`. Change a `delta`, or the numbers under `settings` (`notoriety_points_per_hour`, `notoriety_floor`...), and restart. Her spoken reactions are the `React_...` and `MoodShift_...` lines in `voicepacks/default/personality.json`.

## Notes

- Combat mode is read from the game's Status file (combat vs analysis mode), plus: hardpoints out, or being attacked in the last 45 seconds.
- Slave trading is spotted from the cargo type containing the word `slave`. Other illegal goods use the game's own illegal / stolen / black-market flags.
- During `--demo` her mood is not saved.

## Neutral, swearing and flirting (added in Phase 6)

- **Neutral** is the fifth mood. She starts there and drifts back to it when nothing is going on. She is calm and professional,
  with short dry remarks ("All systems nominal.") and names like Pilot or Captain.
- **Strong language** (Personality page) now works in **every** mood, not just the cross ones. Friendly and Close get warm swearing
  ("You're bloody brilliant"), Neutral gets dry swearing, Sarcastic and Frustrated stay nasty. Turn it off and none of these lines are used.
- **Flirty and naughty when she's very happy** (Personality page, off by default). Only in the **Close** mood (or Friendly/Neutral while she is
  affectionate about the exobiology you carry). Cheeky double meanings about flying, never explicit. With strong language on, a few
  are cheekier. Never added to safety warnings or in "info" style.
