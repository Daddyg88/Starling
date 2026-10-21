# "What are we doing today?" (0.24.0)

When you load into the game she says hello as usual. As soon as she has finished, she asks **"What are we doing today?"**
If you start Starling while you are already playing, she asks about 30 seconds after start-up instead.
She asks once per login, and only while listening is on.

Answer in your own words:

| You say something like | She understands |
|---|---|
| "I think we shall go out exploring" | Exploring |
| "maybe we will go mining today" | Mining |
| "some bounty hunting", "a bit of combat" | Combat |
| "trading", "hauling cargo" | Trading |
| "scan some bio planets", "exobiology" | Exobiology |
| "hunt Thargoids", "anti xeno" | Anti-Xeno |
| "nothing really", "surprise me" | No plan (no points either way) |

**The secret:** each time she asks, she picks ONE of the six that she is not in the mood for. You don't know which.

- Pick that one: she grumbles, says she will go anyway, and you lose 1 mood point.
- Pick any of the other five: she is pleased and you gain 1 mood point.
- Say nothing: nothing happens.

The sentences are in `voicepacks/default/plans.json` (`Plan_Ask`, `Plan_Like_<activity>`, `Plan_Dislike_<activity>`).
The points are the `plan_liked` / `plan_disliked` rules in `config/mood_rules.json`.
Turn it off with Personality page > "Ask me 'What are we doing today?'".

Also in 0.24.0: she no longer says something about engineers when you log in. The game writes a list of every engineer at start-up
and she was reading it out; now she only speaks when you really make progress with one engineer.
