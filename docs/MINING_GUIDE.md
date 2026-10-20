# Mining with Starling (0.19.0)

She now knows when you are mining. She reads the journal lines the game writes while you mine, so nothing needs switching on.

## What she says
- **Prospector limpet fired at a rock:** she reads out the best thing inside and how much of it ("Platinum! 23 percent.").
  - **Motherlode** (a rock with a big pocket of one mineral): "Motherlode! Painite!"
  - **Top minerals** (excited): Platinum, Painite, Void Opals, Low Temperature Diamonds, Monazite, Musgravite, Serendibite, Grandidierite, Alexandrite, Rhodplumsite.
  - **Good minerals** (pleased, only when at least 10 percent of the rock): Osmium, Palladium, Gold, Bromellite, Benitoite, Silver.
  - **Low content and nothing good:** a short "skip it".
- **Refined into your hold:** she calls out top and good minerals as they arrive. Everything else stays quiet so she does not chatter.
- **Core cracked:** a short line.
- **Quiet moments:** while you are mining she makes mining small talk (platinum, treasure hunting, asking you to let her find prices).

## Her mood
She likes mining and shopping. Finding a motherlode, a top mineral, refining top minerals, cracking a core, and buying a ship or module all raise her mood a little (the usual soft caps and the hourly limit still apply, so it cannot run away). The rules are in `config/mood_rules.json` (ids: motherlode, prospect_top, refine_top, refine_good, crack_core, buy_ship, buy_module).

## Asking questions
- "What have we mined?" - tonnes refined this session and your best find.
- "Where should I sell the platinum?" / "Best price for void opals" / "Who's paying the most?" - she looks up the best buyers near the system you are in. If you do not name a mineral she uses your best find this session.

## Where the prices come from
**Inara does not offer a public price lookup**, so she cannot use it. She uses **Ardent** (https://ardent-insight.com), a free community service built from the same market data as Inara and EDSM. No sign-up and no key.
- It needs the internet. If it cannot be reached she says so.
- Results are kept for 15 minutes. Fleet carriers are left out. Markets older than 7 days are left out.
- She tells you the price, the station, the system, the distance in light years and the landing pad size, plus the second best.
- Switch it off: dashboard > Personality > "Mining: look up the best selling prices online".
- Prices are community reported. Always check the market when you arrive.

## What is a "top" mineral?
The lists are in `mining/minerals.py` (a small table you can edit). They follow the community mining guides (core mining for Painite, Platinum, Void Opals, LTDs and the gems; laser mining for Palladium, Osmium and Gold). Prices change every week, so the tiers are a rule of thumb; the price lookup is the real answer.

## Shopping
She loves shopping. Buying a ship gets a big excited line; modules get a smaller one; docking at a station sometimes gets a "let's go and spend your money" line.

## Not tested from here
Written without the game: the journal field names for mining come from the community documentation, so if a line is missing during your first session, check `logs` and tell me.
