# Starling: what is done and what is left

Kept up to date by hand. Tick a box ([x]) when it is finished and note the version. Last updated at 0.89.1.

## STILL TO DO

### Needs a real-game test (built, not yet confirmed)
- [ ] Red alert banner (0.88.1): does RED ALERT show at the bottom centre, right size, never takes the mouse or focus? The log says "RED ALERT banner shown" when it appears.
- [ ] Red alert switches the cockpit to combat mode.
- [ ] Sub targeting press-ahead (0.88.3): lands on the right part on a heavily armed ship and is faster. The game may drop keys pressed too close together; if so the gap in runner.py (FAST_HOLD / FAST_STEPS) needs widening.
- [ ] Sub targeting backwards (Previous Subsystem) and the "sensors" part name.
- [ ] Left-panel tab commands ("open the contacts tab").
- [ ] Noticing remarks and "looking back" lines (0.89.0): do they feel right, too often or too rare? New combat lines for Friendly, Close and Frustrated moods.
- [ ] No pet names or remarks while in a fight (0.88.1).
- [ ] The Restart-to-update button (needs an exe built with STARLING_LAUNCHER_EXE).
- [ ] Crash 0xc0000409: cause unknown.

### To build
- [ ] Liveliness stage: timing touches (a short reaction before a line, different wording first time versus tenth time).
- [ ] Liveliness stage: viewer and chat awareness on stream, in her own voice.
- [ ] Better understanding: "did you mean...?" fuzzy matching for near-miss commands, using the Yes handling.
- [ ] Better understanding: a "heard but not understood" list on the dashboard where a tap teaches her what it meant.
- [ ] Follow-up commands after sub targeting ("next one", "the drive").
- [ ] More sub-target parts: chaff launcher, heatsink, point defence, shield booster, "next weapon".
- [ ] Pre-generate voice for common lines (cuts "Slow start" delays and CPU).
- [ ] Name the busy background threads in the diagnostics (Woz sees 30 to 55% of one core; the cause is not yet known).
- [ ] Pre-generate chat answers (offered, not done).
- [ ] Crew tab.
- [ ] Website "if something is wrong" feature list.
- [ ] Overlay position memory.
- [ ] Split the big files.
- [ ] Gentle voice mode.
- [ ] Optional: room-light red alert (Hue, Govee and similar) and an EDHM theme.
- [ ] Post-deploy checks: SRV, Nomad, fighter out.
- [ ] A "what changed since last session" line at startup.
- [ ] Guardian ruins, settlement and Canonn data (only if wanted; SRVSurvey is far ahead here).

### Things on the player's side (not code)
- [ ] YouTube chat says 403 forbidden: check the API key's restrictions in Google Cloud (Credentials > API restrictions) and that YouTube Data API v3 is enabled.
- [ ] Night vision is a chord of S + V + R + Right Shift and also deploys a heat sink (V). Give it a shortcut that only uses Shift, Ctrl or Alt, or move heat sink off V.
- [ ] UI_Down shares a key with ResetPowerDistribution (Benny), and UI_Select with PlaceSettlement (Woz).

## DONE (newest first)
- [x] 0.89.0 She notices the night (kills, interdictions, scans, systems, jumps since a scoop), looks back on earlier moments, calm combat lines by mood.
- [x] 0.88.4 Detects chord letters that fire their own action (night vision against heat sink).
- [x] 0.88.3 Sub targeting presses ahead on big ships (about 40% faster in a simulated game).
- [x] 0.88.2 YouTube chat backs off on repeated 403 errors.
- [x] 0.88.1 Red alert no longer speeds her voice up (it caused 100 to 124% CPU); banner rebuilt like the biology box; no pet names or remarks while in a fight.
- [x] 0.88.0 Red alert is a small RED ALERT banner (filter, glow and tint removed).
- [x] 0.87.x Red alert filter, focus fixes, speed 20%, combat mode on red alert.
- [x] 0.86.x Sub targeting by voice, journal read fast only during the command, repeated-part fix, left-panel tabs.
- [x] 0.85.10 and later: periodic update recheck, Restart button, held chat questions (!starling queue), UI Down website rule.
- [x] Woz-log fixes: window-search crash guard, backslash key, keybind warnings logged once, 10-minute CPU report with busiest threads.

## Rules that always apply
- Dialogue stays JSON. Never change the player's keybinds (read-only). No cloud brain.
- Bump core/version.py on every push, add a README "New in x.y.z:" entry, a docs/PHASE6_GUIDE.md line, and run `python3 tools/build_guide.py`.
- Run the full tests (`python3 -m unittest discover -s tests -t .`) before pushing. Say what is untested.
- The secret hardpoints phrase never appears in any list, doc, README or site.
- Do not give any information about Payden.
