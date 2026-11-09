# Starling: what is done and what is left

Kept up to date by hand. Tick a box ([x]) when it is finished and note the version. Last updated at 0.89.4.

## STILL TO DO

### Needs a real-game test (built, not yet confirmed)
- [ ] 0.89.2: 'I meant ...' teaching and 'what did you miss'; small reactions (Hm./Oh./Again.); welcome-back lines for returning chat viewers; sub target chaff, heat sink, point defence, shield booster, ECM, manifest scanner; thread owner names (Windows only, untested).
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
- [ ] Australian voice (MeloTTS, 0.89.3/0.89.4): a tester runs run_try_australian_voice.bat and sends australian_test\log.txt plus a note on the sample (female? good?). Then build a safe one-click install (separate private environment, so it cannot break her normal voice). Older note: a tester installs MeloTTS and listens (is it female and good enough?); then decide on bundling it into the exe, a download button, and running 'prepare her voice' for it.
- [ ] Australian wording pack (mate, no worries) as a personality option (offered, not built).
- [ ] Dashboard list of missed sentences with a tap to teach (the voice version, 'I meant ...', is done).
- [ ] "Next weapon" sub-target command.
- [ ] Read the next Woz zip: the 10-minute CPU line should now say which program file the busy threads started in.
- [ ] Viewer awareness beyond the welcome-back lines (reacting to a run of messages), and remembering viewers between sessions.
- [ ] Follow-up commands after sub targeting ("next one", "the drive").
- [ ] Pre-generate voice for common lines (cuts "Slow start" delays and CPU).
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
- [x] 0.89.3 Optional Australian voice via MeloTTS (built against a pretend model; real MeloTTS untried).
- [x] 0.89.2 Teach-by-voice and miss list, small reactions, welcome-back for viewers, six more sub-target parts, thread owner names. (She already asked 'Did you mean...?' before this.)
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
