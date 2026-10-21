# Dashboard tabs by activity (0.22.0)

Six tabs in the dashboard sidebar, one per thing you do in the game. Each starts with a **"She comments on ..."** switch; turn it off and she stays quiet about that activity. **Safety warnings (under attack, shields, heat, hull, low fuel, etc.) are never silenced by these switches.**

| Tab | Switch | What else is in it |
|---|---|---|
| Combat | She comments on combat | Pips to weapons while firing, also in analysis mode, auto heat sink |
| Exploration | She comments on exploration | Ask about scanning valuable planets, auto honk |
| Exobiology | She comments on exobiology | Wonder aloud about planets with life, gets affectionate when rich |
| Mining | She comments on mining | How chatty while refining, the ten favourite minerals |
| Trading | She comments on trading and shopping | Online price lookups (sell and buy) |
| Anti-Xeno | She calls out Thargoid ships | |

Which events belong to which tab is in `config/categories.json`.

## Anti-Xeno
When you target a Thargoid (scout, cyclops, basilisk, medusa, hydra, orthrus, glaive, titan) she names it, whether or not your hardpoints are out. Her lines are in `voicepacks/default/combat.json` (`ShipTargeted_Thargoid`). This is a first step: the game's journal has more Anti-Xeno events that she does not know yet.
