"""What STARLING currently knows about the game. Updated by the event files."""

from dataclasses import dataclass, field
from typing import Optional

from journal.exobiology import ExobiologyTracker
from journal.bio_predict import BioPredictor
from journal.owned_systems import OwnedSystems
from journal.milestones import GameMilestones


@dataclass
class GameState:
    commander: Optional[str] = None
    ship: Optional[str] = None
    ship_name: Optional[str] = None
    ship_model: Optional[str] = None          # the model the game names ("Caspian Explorer"), as opposed to ship_name (your own name for it)
    system: Optional[str] = None
    station: Optional[str] = None
    docked: bool = False
    in_supercruise: bool = False
    max_jump_range: Optional[float] = None  # ly, from the Loadout event (used for neutron routes)
    fuel_capacity: Optional[float] = None   # main tank size in tonnes
    hull_health: float = 1.0                # 1.0 = 100 percent
    shields_up: bool = True
    latitude: Optional[float] = None        # Status.json, while you are close to a planet (otherwise None)
    longitude: Optional[float] = None
    planet_radius: Optional[float] = None   # metres
    fuel_main: Optional[float] = None       # tonnes in the main tank now (Status.json), for the Home page
    cargo_tons: Optional[float] = None      # tonnes of cargo carried now (Status.json)
    cargo_capacity: Optional[float] = None  # from the Loadout event
    modules: list = field(default_factory=list)   # item names of the ship you fly now (Loadout event), for the limpet reminder
    system_security: Optional[str] = None   # "Low Security" ... from FSDJump / Location
    system_allegiance: Optional[str] = None
    system_population: Optional[int] = None
    exobiology: ExobiologyTracker = field(default_factory=ExobiologyTracker)   # replaced by a saving one in app.py
    bio: BioPredictor = field(default_factory=BioPredictor)   # guesses what lives on planets with biological signals (replaced in app.py)
    milestones: GameMilestones = field(default_factory=GameMilestones)   # round numbers from the Statistics event (saving one in app.py)
    owned: OwnedSystems = field(default_factory=OwnedSystems)   # colonies you own (replaced by a saving one in app.py)
    wanted: bool = False                    # the game says you are wanted where you are (notoriety)
    mining_until: float = 0.0               # time.monotonic() until which she treats you as mining (set by limpet / prospector / refinery events)
    attacked_at: float = -999.0             # time.monotonic() of the last UnderAttack or hull damage
    in_nomad: bool = False                  # the Nomad (a ship-launched vessel) is out; the game reports it as an SRV
    status_flags: int = 0                   # the raw "Flags" from Status.json (gear, lights...), used by voice commands
    status_flags2: int = 0
    selected_weapon: str = ""        # Status.json SelectedWeapon (on foot); empty when none
    suit_energy: object = None        # Status.json suit energy 0-1, only if the game provides one (the manual lists none)
    health: object = None             # Status.json Health, 0-1 on foot (None when absent)
    bodies: dict = field(default_factory=dict)       # body name -> {"temperature": kelvin, "gravity": g} from Scan events
    current_body: Optional[str] = None      # the planet or moon you are near (ApproachBody / SupercruiseExit / Status.json)
    awaiting_discovery: bool = False        # just arrived: the first Scan tells us whether anyone discovered this system
    jet_boosts: int = 0                     # jet cone boosts in the current run (events/jet_cone_boost.py)
    jet_boost_time: Optional[float] = None  # when the last one happened
    game_quit: bool = False                 # the journal said Shutdown: the game is closed, so the overlay hides until you load in again
    star_pos: Optional[tuple] = None        # galaxy coordinates (x, y, z) of the system you are in, from FSDJump / Location
    favourite_ship: Optional[str] = None    # code name of the ship she likes best (personality/favourite_ship.py)
    fsd_target: Optional[str] = None        # the system selected as the jump target (FSDTarget): what "Set Target" does
    route_jumps_left: Optional[int] = None  # RemainingJumpsInRoute from the last FSDTarget
    fleet_carrier_callsign: Optional[str] = None   # your own fleet carrier (CarrierStats), so we know which carrier is yours
    fleet_carrier_system: Optional[str] = None     # where it is now (CarrierLocation, CarrierJump, or docking at it)
    power: Optional[str] = None                    # the Power you are pledged to (Powerplay events)
    squadron: Optional[str] = None                 # your squadron's name, if you are in one (SquadronStartup)
    hge_system: object = None       # the system she last called out High Grade Emissions in (once per system)
    materials: dict = field(default_factory=dict)   # engineering materials held: {"iron": 120, ...} (journal/materials.py)
    nsp_seen: set = field(default_factory=set)   # names of notable stellar phenomena she already told you about this session
    nsp_system: object = None        # the system she last said "there is an NSP here" in
    pending_events: list = field(default_factory=list)   # (name, data) she should announce after this journal line
    gui_focus: int = 0                      # which screen is open (Status.json GuiFocus): 6 = galaxy map
    status_seen: bool = False               # True once Status.json has been read
