# Starling: what is done and what is left

Kept up to date by hand. Tick a box ([x]) when it is finished and note the version. Last updated at 0.89.6.

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
- [ ] Australian voice one-click install (0.89.7) is built but UNTESTED on a real PC: a tester presses 'Install Australian voice' on the Voice page and reports (install log is data/melo_env/install_log.txt). Check idle shutdown and that lines are not choppy. Older notes (0.89.3 to 0.89.5): first try (0.89.4) failed on fugashi and tokenizers (they must be compiled); 0.89.5 installed fine on Windows. First sentence took 16 s (slower than real time) and load took 50 s, so it needs saved lines. Waiting for: the listening verdict (female? good?) and the 0.89.6 speed and memory numbers. Then decide how to install it for everyone (own private environment). a tester runs run_try_australian_voice.bat and sends australian_test\log.txt plus a note on the sample (female? good?). Then build a safe one-click install (separate private environment, so it cannot break her normal voice). Older note: a tester installs MeloTTS and listens (is it female and good enough?); then decide on bundling it into the exe, a download button, and running 'prepare her voice' for it.
- [ ] Australian wording pack (mate, no worries) as a personality option (offered, not built).
- [ ] Dashboard list of missed sentences with a tap to teach (the voice version, 'I meant ...', is done).
- [ ] "Next weapon" (0.89.9) built; needs a real-game try on a ship with several guns.
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
- [ ] "Last time out" recap line at login (0.89.9) built; listen for how it sounds in the game.
- [ ] Guardian ruins, settlement and Canonn data (only if wanted; SRVSurvey is far ahead here).

### Things on the player's side (not code)
- [ ] YouTube chat says 403 forbidden: check the API key's restrictions in Google Cloud (Credentials > API restrictions) and that YouTube Data API v3 is enabled.
- [ ] Night vision is a chord of S + V + R + Right Shift and also deploys a heat sink (V). Give it a shortcut that only uses Shift, Ctrl or Alt, or move heat sink off V.
- [ ] UI_Down shares a key with ResetPowerDistribution (Benny), and UI_Select with PlaceSettlement (Woz).

## DONE (newest first)
- [x] 0.89.8 Updater moves her files instead of copying (confirmed: no longer sticks). Red alert banner confirmed in place.
- [x] 0.89.7 Australian voice one-click install in a private environment + worker (untested on real Windows).
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

## Settlement maps (0.92.0)
- [x] All 28 Odyssey layouts traced by eye from the Odyssey Map Guide (maps/settlements/*.json, all marked PROTOTYPE). Pad counts for everything except Tourist 1/Industrial 2 are guesses from the pictures; several layouts share a pad count, so she only suggests a map when exactly one matches, otherwise say "show settlement map <name>". Needs real visits to confirm pad counts, airlock/door colours and positions.
- [ ] Prototype wireframe map Tourist 1 (maps/settlements/tourist_1.json), overlay (ui/settlement_overlay.py), voice "show settlement map tourist one" / "hide settlement map". Credit: CMDR Quizengine's Odyssey Map Guide (maps/settlements/CREDITS.md). Still to add: credit in README + website when shipped.
- [ ] Settlement recorder (navigation/settlement_recorder.py) writes data/settlement_samples.json (journal details, on-foot trail, voice marks "mark spot <name>"); goes into the diagnostics zip. Needs real visits to learn: what the approach coordinates mean, how pad counts (LandingPads) match layouts, whether Status Heading works on foot.
- [ ] Then: group (StationEconomy) + pad counts -> suggest layout; two-point calibration; position/heading arrow on the map.
- [x] 0.92.0: rotation finder from terminals alone, auto show/hide, north-up map, 'you are here', voice arrow (nearest terminal, power plant, alarm, door, airlock, ship).
- [ ] Real-game tests: overlay on screen, arrow, whether standing still 6 s = a terminal works at other settlements (terminals write no journal line and no screen number on foot), pad counts (26 of 28 are picture readings, unconfirmed), whether the scale (about 0.325 m per unit) is the same at every settlement, in-ship heading.
- [ ] Shared calibrations file shipped with the app once testers have visited settlements.
- [ ] Add each visited settlement to maps/known_settlements.json (MarketID -> layout) once its layout is confirmed; Cheesebeard's Cave (4385255427, Extraction, one large pad) layout still unknown.
- [ ] Collect testers' diagnostics zips and run tools/merge_calibrations.py so more settlements ship lined up (needs the pad counts fixed first so layouts are chosen right).
- [x] Benny read the pad counts for all 28 layouts from the Odyssey Map Guide (0.93.1, in maps/settlements/*.json + test). Still best guesses from pictures: confirm against real LandingPads as settlements are visited.

- [ ] 0.94.0 chat awareness: check on a real stream that Twitch's anonymous reader delivers subs, gifts, raids and watch streaks (USERNOTICE), and that YouTube Super Chats and members arrive. Follows need a Twitch login (not built).
- [ ] 0.95.0: check in the real game that habit remarks land at calm moments (Docked, FSDJump), that the late-night and system remarks sound right, and that push-to-talk cuts her off. Maybe later: she listens for your answer when she asks 'why do you keep going back to...?' and remembers it (needs the answer listener).
- [ ] 0.95.1: collect zips with the new trail flags; look for a flag that changes when going into or out of a building (a way to line up with no terminals). Check in the real game that three stops line up and that the fixed map size (0.325) holds at more settlements; Sharma Hydroponics Farm is Agriculture 4 (pads 2S 1L confirmed by the journal).
- [ ] 0.95.2: in the real game, land on pad 1 at a SECOND settlement of a layout we have already lined up (for example another Industrial 2) and check the map is lined up from the landing and that two terminal stops confirm it. Collect zips so more layout frames can be shipped (maps/map_frames.json). Check the corrected pad counts (Agriculture 3 and 5, Extraction 1, Industrial 3 and 5, Military 1, 3, 4, 5, Tourist 2) against the journal as they come up. Peng Synthetics Foundry and Makubuya Engineering Silo are listed as Industrial 2 (very likely, not certain): land on pad 1 at either and check the map is lined up from the landing (0.95.3).
- [ ] 0.95.4: ask the tester with the damaged spaCy model to update and start Starling once with internet: check the log says the language helper was reinstalled and the voice loads. Consider retrying the microphone if it is not ready at start.
- [ ] 0.96.0: in the real game, switch Mood control to Random and watch her mood change after 20 minutes; play a bit, switch back to Automatic and check the Home score is what it was. Check Red alert now sits at the bottom of the Combat page with its two buttons. Decide whether random mood changes should be announced out loud.
