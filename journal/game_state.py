"""What STARLING currently knows about the game. Updated by the event files."""

from dataclasses import dataclass, field
from typing import Optional

from journal.exobiology import ExobiologyTracker


@dataclass
class GameState:
    commander: Optional[str] = None
    ship: Optional[str] = None
    ship_name: Optional[str] = None
    system: Optional[str] = None
    station: Optional[str] = None
    docked: bool = False
    in_supercruise: bool = False
    max_jump_range: Optional[float] = None  # ly, from the Loadout event (used for neutron routes)
    fuel_capacity: Optional[float] = None   # main tank size in tonnes
    hull_health: float = 1.0                # 1.0 = 100 percent
    shields_up: bool = True
    fuel_main: Optional[float] = None       # tonnes in the main tank now (Status.json), for the Home page
    cargo_tons: Optional[float] = None      # tonnes of cargo carried now (Status.json)
    cargo_capacity: Optional[float] = None  # from the Loadout event
    system_security: Optional[str] = None   # "Low Security" ... from FSDJump / Location
    system_allegiance: Optional[str] = None
    system_population: Optional[int] = None
    exobiology: ExobiologyTracker = field(default_factory=ExobiologyTracker)   # replaced by a saving one in app.py
    wanted: bool = False                    # the game says you are wanted where you are (notoriety)
    in_nomad: bool = False                  # the Nomad (a ship-launched vessel) is out; the game reports it as an SRV
    status_flags: int = 0                   # the raw "Flags" from Status.json (gear, lights...), used by voice commands
    status_flags2: int = 0
    status_seen: bool = False               # True once Status.json has been read
