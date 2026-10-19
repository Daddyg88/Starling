# Her brain (0.18.0)

No AI model, no download, no extra CPU: it is a big set of recognised questions and answers, with the real game mixed in. It is instant, safe and works offline.

**How to use it:** say her name (or hold push-to-talk) and ask. It is only used when you are talking to HER and the sentence is not a game command, so it can never steal a command. Switch it off on the Personality page ("Her brain").

## Things to try (great on stream)
- **About her:** "what's your favourite colour / food / music / ship", "do you dream", "do you sleep", "are you scared of anything", "do you have feelings", "do you get lonely", "how old are you", "are you single", "are you smart", "what do you want", "what do you do for fun", "do you like me", "what do you think of the Thargoids / Guardians / fleet carriers / humans".
- **About the game (live):** "where are we", "what ship am I flying", "status report", "am I wanted", "what should we do", "how long have we been playing", "what time is it", "what's the date", "what's my name".
- **Fun:** "tell me a riddle" (then guess, or "I give up"), "write me a poem", "tell me a story", "tell my fortune", "roast me", "compliment me", "give me a nickname", "give me a pickup line", "tell me a space joke", "tell me a fun fact", "tell me a secret", "would you rather", "flip a coin", "roll a dice", "roll a d20", "pick a number between 1 and 100", "magic 8 ball" or any "should I ...?" question.
- **Feelings:** "cheer me up", "I'm tired", "I'm hungry", "I'm angry", "I'm happy", "sorry", "wow", "that was close", "oops", "we won".
- **Stream:** "say hello to chat", "introduce yourself to the viewers", "thank you chat", "say goodbye to chat", "remind chat to follow", "hype up chat", "what can you do", "show off", "what's new".
- **Follow-ups (she remembers the last topic for about 2 minutes):** "why?", "tell me more", "what about you?", "really?".
- **Opinions on anything:** "what do you think about <anything short>".

## Changing it
- `voicepacks/default/brain.json`: her answers. One list per topic, plus `_Friendly`, `_Close`, `_Sarcastic`, `_Frustrated` for moods, `_More` / `_Why` / `_You` / `_Really` for follow-ups. Mature lines use `{"text": "...", "mature": true}` and need the mature setting on.
- `config/brain_intents.json`: which sentences mean which topic (regular expressions on lower-case text with no punctuation or apostrophes). The first match wins.
- `voicepacks/default/riddles.json`: the riddles.
- After adding lines, press **Prepare her voice now** (Voice page) so she can say them instantly.

## Honest limits
It only knows what is written. A question nobody planned for gets the normal "I didn't catch that". A real language model (optional, later) would be for those. Game answers use only what the game tells her (system, ship, hull, shields, wanted, time), not credits or fuel level.
