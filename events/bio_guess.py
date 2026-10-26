"""
Exobiology guesses, made up by STARLING (pending events) from journal/bio_predict.py:

  BioGuess    after the system scanner (FSS): "two biological signals on A 3, probably Stratum or Tussock, around 4 million"
  BioTopHint  a top-ten species could live there: "you might find Stratum Tectonicas on that planet"
  BioRefined  after the surface scan: the real genera (and whether her guess was right)
Her words are in voicepacks/default/exobiology.json.
"""

from core.event_bus import LOW, NORMAL
from events.base_event import BaseEvent


class BioGuess(BaseEvent):
    name = "BioGuess"
    priority = NORMAL
    source = "status"
    summary = "{Signals} on {Body}: {Guess}"


class BioTopHint(BaseEvent):
    name = "BioTopHint"
    priority = NORMAL
    source = "status"
    summary = "{Species} could be on {Body}"


class BioRefined(BaseEvent):
    name = "BioRefined"
    priority = NORMAL
    source = "status"
    summary = "Surface scan of {Body}: {Found}"


class BioProgress(BaseEvent):
    name = "BioProgress"
    priority = LOW
    source = "status"
    summary = "{Count} species in the codex"


class UniqueBio(BaseEvent):
    name = "UniqueBio"
    priority = NORMAL
    source = "status"
    summary = "{Species}: the one-of-a-kind species"
