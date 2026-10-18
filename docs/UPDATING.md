# Updating Starling without losing your settings

1. Close Starling.
2. Unzip the new zip **over** your existing Starling folder (choose "Replace files").
3. Start it as normal.

Your settings live in `config/settings.json` and your saved data lives in `data/`.
Updates no longer contain either file, so unzipping never overwrites them.
Starling also keeps `config/settings.json.bak`, a copy of your previous settings, in case anything goes wrong.

New options added in an update get sensible defaults automatically.

Note: if you hand-edited `config/events.json`, `config/speech.json` or `config/mood_rules.json`, an update will replace them. Copy them somewhere first.

## Your mood is kept too
Her mood score, the paintwork estimate and the list of facts she has already told you live in the `data` folder (`data/mood.json`, `data/facts_seen.json`). Updates never contain that folder, so unzipping over the old one keeps them.
`data/mood.json.bak` is a copy of the previous save, just in case.

If you ever unzip into a NEW folder, copy the old `data` folder and `config/settings.json` across first.
