# Start here (for everyone, no computer skills needed)

Starling is a voice companion for Elite Dangerous. This page takes you from nothing to talking to her. It takes about 15 minutes, most of it waiting.

## 1. Get it
1. Open the Starling **Releases** page on GitHub and download **Starling.exe** from the newest release.
2. Put it anywhere you like (the desktop is fine) and double-click it.

## 2. If Windows or your antivirus complains
This is normal for a new, small program. Starling.exe is not signed with a paid publisher certificate, so Windows treats it as "unknown". The full source code is public on GitHub for anyone to read.

- **"Windows protected your PC" (blue box):** click **More info**, then **Run anyway**.
- **Your antivirus removed or blocked it:** open the antivirus, find the quarantine or "protection history", **restore** Starling.exe, and allow it. If it keeps happening, add an exclusion (an "allowed" folder) for `%LOCALAPPDATA%\Starling` and for the place you saved Starling.exe.
- **The download itself is blocked by your browser:** choose "Keep" in the browser's downloads list.

If you are not sure it is safe, ask the person who gave you the link.

## 3. The first start (be patient)
The first time, Starling.exe shows a small window while it sets itself up: it downloads Starling, installs Python for you (no administrator rights needed) and installs her add-ons. **This takes several minutes. It is not frozen.** Keep your internet on and leave it alone. Later starts take a couple of seconds.

## 4. The "Get started" page
When Starling opens you land on **Get started**. It is a checklist. A green tick means that part is ready. Anything else has a button:

| Line | What it does |
|---|---|
| Elite Dangerous | Checks she can see Elite's journal. Start the game once if it says it can't. |
| Her voice | Press **Say hello** to hear her. The first start can take a minute. |
| Listening to you | Press **Turn listening on**, then close and reopen Starling once. |
| How well she hears you | Press **Use Balanced** if offered. She hears you much better. |
| Your Elite keys | Press **Check my Elite keys**. See below. |

When you are happy, press **I'm done - go to Home**. You can open Get started again from the menu on the left.

## 5. Your Elite keys (the one thing you must do in the game)
When you say "landing gear" or "launch", she presses **your own keyboard key** for it. She never changes your keys. If an action only has a joystick button, she can't press it for you, so give it a keyboard key as well:

1. In Elite open **Options > Controls**.
2. Find the action she says is missing and give it a keyboard key.
3. Press **APPLY**, then press **Check my Elite keys** again.

Keys that are shared by two actions can make Elite do the wrong thing, so she lists those too.

## 6. Talking to her
Say her name, then what you want: "Starling, landing gear", "Starling, launch" (while docked), "Starling, how are you?". Speak clearly and a little slower than normal.

## 7. If something goes wrong
- The dashboard's **Developer** page has **Copy my log to the clipboard**. Paste it into a message to whoever looks after Starling for you.
- `docs/TROUBLESHOOTING.md` lists the common problems.
