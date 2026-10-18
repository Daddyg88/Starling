# Phase 7 - Memory (0.12.0)

Starling now remembers milestones and brings them up herself. Everything is stored on YOUR computer in `data/tetko.db`. Nothing is sent anywhere.

## What she remembers
- your longest jump, biggest biology sale and biggest exploration sale (only replaced when you beat them)
- every time you were destroyed (the last 10), and by whom
- big missions (5 million credits or more)
- the first time you sample each species
- counters: hours together, jumps made, missions done, times destroyed

## How she uses it
- At login she mentions ONE memory (the one she has said least often).
- Ask: **"Starling, what do you remember?"**
- She will not wipe her memory by voice, on purpose.

## Dashboard > Memory
- switch remembering on or off, and the login mention on or off
- **Show what she remembers** lists it all
- **Forget everything** asks first, then deletes memories and counters

## Her words
`voicepacks/default/memory.json` - edit freely. Keys ending `_Login` are for the greeting, `_Ask` for your question.

## Test it
1. Update (Starling.exe does it by itself after the release is published).
2. Make a jump, then say "Starling, what do you remember?" - she should mention the jump.
3. Open Dashboard > Memory > Show what she remembers.
