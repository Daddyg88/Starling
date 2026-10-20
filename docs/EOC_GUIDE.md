# The East Orion Company (0.20.0)

She now knows the company: a massive organisation that owns whole star systems, each built by one of its Commanders.

## Things to say
- "Tell me about the East Orion Company" (or "the EOC") - overview, then say **"tell me more"** and she takes you round the systems one by one.
- "Who is the CEO?" - names the CEO. If your Commander name is on the CEO list she says it's you.
- "Which systems does the EOC own?" - lists them all.
- "Tell me about Arcadia / Milliways / Payden's Haven / Rancid Roquefort / Winter Station..." - also works with station or builder names ("tell me about Curd Nerd", "the Pensioner Retreat").
- If you built one of the systems she says so ("That one is yours, Commander").

## Where the facts are
`config/eoc.json`. It holds the CEO list, the systems (name, game system, builder, other names, what she says, stations) and a `pilots` list for company Commanders she should recognise (empty for now; the list can be added there). Her framing words are in `voicepacks/default/eoc.json`.
Updates replace this file, so send new systems to me and I will add them to the next release.

## Known systems
Danforth (home), Arcadia, Black Legacy, Baskerville Ring, Payden's Haven, Winter Station, Rhino Heaven, Milliways, Rancid Roquefort.
Her old back story called the company "small"; it now says it is vast.
