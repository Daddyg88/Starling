# Starling pose shot list (for ComfyUI + Wan 2.2)

Start every clip from the SAME picture: `starling_base_512x768.png` (512 x 768). Frames below are at 24 fps (49 = 2 s, 73 = 3 s, 97 = 4 s, 121 = 5 s).
Name the file with the clip name, e.g. `nod.mp4`. Make 2 or 3 tries of each and keep the best.

**Add to the START of every prompt:** `a blue glowing hologram woman, upper body, static camera, no zoom, plain black background, she starts in a calm neutral pose,`
**Add to the END of every prompt:** `and then returns to the same calm neutral pose, smooth, same lighting`
**Negative prompt (every clip):** `camera movement, zoom, text, watermark, extra people, hands covering face, changing clothes, flicker, blur, cartoon`

## Tier 1 - do these first (she already has the slots, or does them most)

| # | Clip name | Used for | Frames | Prompt (middle part) |
|---|---|---|---|---|
| 1 | `pleased` | missions done, big sales, milestones | 73 | she smiles warmly, eyes close for a moment, then opens them happy and proud |
| 2 | `thinking` | while she works out an answer | 97 | she looks slightly up and to the side, thoughtful, a small slow tilt of the head, lips together |
| 3 | `listening` | while you talk to her | 97 | she looks straight at the viewer, attentive, a tiny slow nod and a slight head tilt, eyebrows slightly raised |
| 4 | `bored1` | quiet for a long time | 97 | she glances to the side, lets out a small sigh, shifts her weight, looks around |
| 5 | `bored2` | quiet for a long time | 97 | she rests her chin on one hand, looks off to the side, blinks slowly |
| 6 | `salute` | game closes | 73 | she raises her right hand to her brow in a neat salute, smiles, lowers it |
| 7 | `nod` | docking granted, wing joined, "yes" | 49 | she nods her head twice, small, confident |
| 8 | `shake` | docking denied, mission failed, "no" | 49 | she shakes her head slowly side to side, lips pressed, disappointed |
| 9 | `startle` | interdicted, under attack, hull damage | 49 | her eyes widen, she flinches back slightly in alarm, then steadies |
| 10 | `laugh` | funny moments, jokes | 73 | she laughs out loud, shoulders shaking, eyes crinkled, then settles with a grin |

## Tier 2 - the personality clips

| # | Clip name | Used for | Frames | Prompt (middle part) |
|---|---|---|---|---|
| 11 | `wink` | cheeky or flirty lines | 49 | she gives a playful wink with her right eye and a small smile |
| 12 | `smirk` | innuendo, teasing | 73 | she raises one eyebrow and gives a sly smirk, looking at the viewer |
| 13 | `blush` | flustered, compliments | 73 | she looks down shyly, smiles, glances up through her lashes |
| 14 | `blow_kiss` | affection, thank you | 73 | she blows a kiss toward the viewer with one hand, smiling |
| 15 | `eyeroll` | sarcastic lines | 49 | she rolls her eyes upward with a tired half smile, then looks back |
| 16 | `facepalm` | silly mistakes | 73 | she briefly puts one hand to her forehead, shakes her head, lowers the hand with an amused sigh |
| 17 | `shrug` | "I don't know" | 49 | she shrugs both shoulders, tilts her head, small apologetic smile |
| 18 | `sad` | deaths, lost cargo, bad news | 97 | her smile fades, she looks down sadly, a slow breath, then looks up softly |
| 19 | `worried` | low fuel, danger | 73 | she looks anxious, brows drawn together, glances to one side, bites her lip |
| 20 | `angry` | being shot, griefers | 73 | her brows lower, jaw tightens, she narrows her eyes in a stern glare |

## Tier 3 - Elite moments

| # | Clip name | Used for | Frames | Prompt (middle part) |
|---|---|---|---|---|
| 21 | `awe` | beautiful planets, huge finds, unique life | 97 | her eyes go wide with wonder, lips part in a soft gasp, she looks slowly upward in amazement |
| 22 | `excited` | big discoveries, first footfalls | 73 | she lights up with excitement, bright smile, a small happy bounce |
| 23 | `sleepy` | long sessions, very quiet | 121 | she yawns, covering her mouth with her hand, blinks slowly, her eyes grow heavy |
| 24 | `point` | "look there", route, markers | 73 | she points to her left (the viewer's right) with one finger and looks that way, then back |
| 25 | `thumbs_up` | good news, confirmations | 49 | she gives a clear thumbs up and a confident smile |
| 26 | `facing_away` | scanning, heads-down work | 97 | she turns her head to look to one side, focused, as if reading a screen, then turns back |
| 27 | `cheer` | wins, streams hitting a goal | 73 | she raises both fists in a small cheer, smiling widely, then lowers them |
| 28 | `idle_alt1` | extra variety while idle | 121 | she breathes slowly and blinks, her hair drifts gently, a tiny smile appears and fades |

## Tips so they work first time

* If she drifts, say `locked camera, her position does not change`.
* If the end does not match the start, add `ends exactly as it began`; Starling's tool can also cross-fade the ending.
* Keep arms and hands inside the picture; clips that go out of frame are cut off (only `salute` has room at the side).
* Do not use any prompt with text or logos; the AI will draw them.
* Save as mp4, any name; send them to me in batches of 5 to 10.
