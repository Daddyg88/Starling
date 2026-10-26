# Mining with Starling (0.21.0)

She now knows when you are mining. She reads the journal lines the game writes while you mine, so nothing needs switching on.

## What she says
- **Prospector limpet fired at a rock:** she reads out the best thing inside and how much of it ("Platinum! 23 percent.").
  - **Motherlode:** "Motherlode! Painite!"
  - **Your ten favourites** (excited): chosen on the dashboard, **Mining page** (ten boxes). Starting ten: Platinum, Painite, Void Opals, Low Temperature Diamonds, Monazite, Musgravite, Serendibite, Grandidierite, Alexandrite, Rhodplumsite.
  - **Good minerals** (pleased, at least 10 percent of the rock): Osmium, Palladium, Bromellite, Benitoite. **Gold and silver are ignored** unless you put them in a box.
  - **Low content and nothing good:** a short "skip it".
  - **Depleted rock:** if the prospector reports nothing left she says the asteroid is depleted, and "nearly empty" under 15 percent left.
- **Refined into your hold:** she does NOT call out every tonne. The first of each good mineral, then every 5 tonnes (3, 5 or 10, see "How chatty" on the Mining page), the odd cheer for a favourite, and a running total. Everything else stays quiet.
- **Core cracked:** a short line.
- **Quiet moments:** mining small talk (about 30 different lines).

### About "depleted"
Elite does not write a "depleted" line in the journal. She knows when you fire a prospector at a rock again and it reports little or nothing left (the game's Remaining figure). If you want her to say it without re-prospecting, tell me and I can add a guess based on the refining stopping.

## Her mood
She likes mining and shopping. Finding a motherlode, a top mineral, refining top minerals, cracking a core, and buying a ship or module all raise her mood a little (the usual soft caps and the hourly limit still apply, so it cannot run away). The rules are in `config/mood_rules.json` (ids: motherlode, prospect_top, refine_top, refine_good, crack_core, buy_ship, buy_module).

## Asking questions
- "What have we mined?" - tonnes refined this session and your best find.
- "Where can I buy tritium?" / "cheapest liquid oxygen" / "who sells ..." - the cheapest nearby sellers that have stock.
- "Where should I sell the platinum?" / "Best price for void opals" / "Who's paying the most?" - she looks up the best buyers near the system you are in. If you do not name a mineral she uses your best find this session.

## Where the prices come from
**Inara does not offer a public price lookup**, so she cannot use it. She uses **Ardent** (https://ardent-insight.com), a free community service built from the same market data as Inara and EDSM. No sign-up and no key.
- It needs the internet. If it cannot be reached she says so.
- Results are kept for 15 minutes. Fleet carriers are left out. Markets older than 7 days are left out.
- She tells you the price, the station, the system, the distance in light years and the landing pad size, plus the second best.
- Switch it off: dashboard > Personality > "Mining: look up the best selling prices online".
- Prices are community reported. Always check the market when you arrive.

## Void Compass and Inara
Void Compass does not use Inara either: its Trading tab gets prices from Spansh. Its Local API (the thing Starling talks to) is only documented for overlays and voice, with no trade lookups I can call, so Starling uses Ardent directly. You get the same job done by voice without opening Void Compass.

## What is a "top" mineral?
The ten favourites are your choice (Mining page); the calmer list is in `mining/minerals.py`. They follow the community mining guides (core mining for Painite, Platinum, Void Opals, LTDs and the gems; laser mining for Palladium, Osmium and Gold). Prices change every week, so the tiers are a rule of thumb; the price lookup is the real answer.

## Shopping
She loves shopping. Buying a ship gets a big excited line; modules get a smaller one; docking at a station sometimes gets a "let's go and spend your money" line.

## Not tested from here
Written without the game: the journal field names for mining come from the community documentation, so if a line is missing during your first session, check `logs` and tell me.


## Where to sell (0.23.0)

Ask: "Starling, where should I sell the platinum?" (or just "where should I sell this" after refining).

What she searches for (numbers live at the top of `mining/prices.py` if you want to change them):

- Stations within **1000 light years** of the system you are in.
- Prices reported in the last **1 day**.
- Stations that want at least **1000 tons**.
- **Large landing pads only**. Fleet carriers are left out.

She then says the two best as **the first one** and **the second one** (price per tonne, tons wanted, station and system), and asks "the first one or the second one?".
Answer "A", "option b", "the second one", "bravo" (or "neither"). A plain "yes" means A, the better price.
She then asks "Would you like me to plot a route for you?". Say yes and she copies that system's name to your clipboard and runs the same galaxy map macro as "plot the next waypoint" (no Spansh route is worked out; voice commands must be on). Saying nothing just drops it.
Buying ("where can I buy ...") keeps its old, gentler search. The sentences are in `voicepacks/default/selling.json`.


## Nearest or best (0.23.1)

The same sentence can ask for two different things:

- **Best** (the default): "where can I sell this platinum for the best price" gives the highest price to sell, or the lowest price to buy.
- **Nearest**: any of "nearest", "closest", "nearby", "close by", "near here", "quickest" in the sentence, for example
  "where is the nearest place to sell this" or "where can I buy tritium nearby". The closest two come first and she says how far away each is.
  For selling, "nearest" still needs large pads and prices from the last day, but accepts stations wanting only 100 tons (`NEAREST_MIN_DEMAND` in `mining/prices.py`).

Buying now works like selling: the first one and the second one (price, tons in stock, station, system, distance), then "the first one or the second one?" and the offer to put the chosen system into the galaxy map.


## More talk, and pips in analysis mode (0.24.1)

- New lines are in `voicepacks/default/mining2.json`. Big pools now remember up to 12 recent lines, so a line is not heard again soon.
- She sometimes remarks on an ordinary mineral, cheers for good minerals too, and now and then comments when you launch a prospector or collector limpet.
  The Mining page's "How chatty" box (quiet / normal / chatty) controls all of it; "quiet" keeps her silent about these extras.
- While mining she chats about twice as often as usual.
- Pips: when you hold a fire button in analysis mode she now sends 6 presses to weapons (extra presses do nothing when full),
  tops the weapons up every 8 seconds while you hold the laser, and waits 3 seconds after you let go before resetting.
  If it still does not work, open `logs/starling.log` and look for "Combat assist watches these fire buttons" - that line names
  every button she is watching. If your mining trigger is not in it, add it in `config/settings.json` under `combat_assist` > `fire_buttons`.

## Limpet reminder (0.48.3)
When you dock at a station with a market, she reminds you to buy limpets, but only if the ship you are flying RIGHT NOW has all three: a refinery, a collector limpet controller and cargo racks (any size). She reads this from the game's Loadout, so changing ship or modules is picked up by itself. She stays quiet if you already carry 10 or more limpets, or the station has no commodity market. Switch: Mining page > "Remind me to buy limpets when I dock".
Honest limit: the module names were written from the journal manual, not tested in your game. If she never reminds you, send me the log and a line from your Loadout.
