"""
EVERYTHING STARLING CAN DO BY VOICE - one entry per command.

TO ADD A COMMAND: add one  C(...)  entry to CATALOG below. Nothing else needs touching.

    C("galaxy_map",                      a short id (unique)
      "GalaxyMapOpen",                   the action's name in Elite's .binds file (see docs/PHASE6_GUIDE.md)
      "the galaxy map",                  how she names it when she answers
      on=[...], off=[...], toggle=[...], press=[...],     what you can say (templates, see below)
      doing={...},                       what she says she is doing
      flag=(field, bit),  words=("down", "up"),           OPTIONAL: lets her notice "already down"
      strict=True)                       OPTIONAL: only act on a near-perfect hearing (for big actions)

Templates are short and get expanded into every combination:
    (a|b|c)   pick one of these          [the]   optional word
    {OPEN_V}  a shared list of verbs (see MACROS)
So  "{OPEN_V} [the] galaxy map"  covers "open the galaxy map", "pull up galaxy map", "show galaxy map"...
Words like "the", "my", "please", "could you" are ignored automatically, and a few nouns are merged
(wheels / undercarriage / landing gear -> gear), so you rarely need to list those.

Intents:  on = switch on / open / lower / deploy     off = switch off / close / raise / retract
          toggle = flip it whatever it is now        press = just press the key
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

MACROS = {
    "OPEN_V": "(open|show|display|bring up|pull up|launch|access|load|go to|check|look at|view|call up|take me to|get)",
    "CLOSE_V": "(close|hide|dismiss|exit|leave|shut|get rid of|back out of|cancel|remove|put away|stop showing)",
    "ON_V": "(turn on|switch on|enable|activate|engage|start|power up|fire up|put on|use|bring on)",
    "OFF_V": "(turn off|switch off|disable|deactivate|disengage|stop|shut off|kill|cut|power down|put off|end)",
    "DEPLOY_V": "(deploy|extend|lower|drop|put out|release|arm|bring out|put down|let down|open)",
    "RETRACT_V": "(retract|raise|stow|pull in|withdraw|close|lift|fold|tuck|disarm|holster|put away|bring in|pull up)",
    "FIRE_V": "(fire|launch|deploy|use|drop|pop|activate|release|throw out|shoot|send)",
    "REQUEST_V": "(request|ask for|get|call for|put in for|send|make|do|can I get|I need|I want|I would like|give me)",
    "TOGGLE_V": "(toggle|flip|switch|change|swap)",
    "TARGET_V": "(target|select|lock|lock on to|lock onto|cycle to|switch to|go to|pick)",
    "SET_V": "(set|change|put|move|go to|select|use|give me|bring)",
}


# Macros are lists of steps. A step is an Elite action name from your controls ("FocusLeftPanel"),
# "Name x3" to press it three times, or "wait 0.5" to pause. You can replace any macro in config/settings.json:
#   "macros": { "request_docking": ["FocusLeftPanel", "wait 0.8", "UI_Select"] }
# Docking, taken from a real recording of the commander on the X52 (0.10.4): focus the left panel, wait for it to open,
# Next Tab twice (Navigation to Contacts), Right, Select (that sends the request; the game answered 0.35 s later),
# wait, then Back to close the panel. The waits are the commander's own pace: lower them in config/settings.json if
# you want it faster (macros.request_docking).
# 0.34.4: back to the step that worked in 0.10.4 (Right before Select, so the cursor is on the request button), then the
# commander's 0.34.0 recording for the close-out: Select, Previous Tab twice, Back.
DOCKING_MACRO = ("FocusLeftPanel", "wait 1.2", "CycleNextPanel x2", "wait 1.2", "UI_Right", "wait 0.7",
                 "UI_Select", "wait 1.45", "CyclePreviousPanel x2", "wait 0.75", "UI_Back")
# Nomad, as the commander described it: look down at the helm menu (the bottom / role panel), press down once, then right once.
# Then Select to launch it. You can change these steps in config/settings.json (macros.deploy_nomad).
# Auto launch from a station: Select on the Launch button of the station menu. Only works while docked (see core/app.py). If
# your menu needs more presses, put your own steps in config/settings.json under macros.auto_launch.
# 0.34.2: the commander's second recording (13:25). Left panel: Next Tab x2, Previous Tab x2, Back to close it. Right
# panel: Next Tab x5, Previous Tab x5, Back to close it. Then wait for the panels to go, Down and Select (Launch). The last
# two are the menu keys (UI_Down / UI_Select), the same buttons the recorder showed as ResetPowerDistribution / SelectTarget.
# (0.34.0/0.34.1 closed the panels with the focus button instead of Back, so the Down and Select probably hit the panel.)
# 0.34.4: "say Launch_Start" and friends make her talk her way through it ("I have control", "checking systems"...).
LAUNCH_MACRO = ("say Launch_Start", "FocusLeftPanel", "wait 1.35", "CycleNextPanel x2", "wait 0.9", "CyclePreviousPanel x2",
                "wait 1.1", "UI_Back", "wait 0.9", "FocusRightPanel", "say Launch_Systems", "wait 1.25", "CycleNextPanel x5",
                "wait 0.25", "CyclePreviousPanel x5", "wait 0.9", "UI_Back", "say Launch_Go", "wait 2", "UI_Down", "wait 0.6",
                "UI_Select")
NOMAD_MACRO = ("FocusRadarPanel", "wait 0.8", "UI_Down", "wait 0.2", "UI_Right", "wait 0.2", "UI_Select")

# Plot the next neutron waypoint, hands free (the clipboard already holds its name, see navigation/route.py).
# Taken from a real recording of the commander on the X52 (0.10.5): open the galaxy map, Up to the search box, Select to
# click into it, paste, Select the result, wait while the map flies there, HOLD Select to set it as
# the target (the game then reports NavRoute), wait, then Back twice to close the map. The waits are the commander's own
# pace; tune them in config/settings.json under macros.plot_waypoint.
PLOT_MACRO = ("GalaxyMapOpen", "wait 2.5", "UI_Up", "wait 1.2", "UI_Select", "wait 1.3", "paste", "wait 1.5",
              "UI_Select", "wait 4.0", "hold CamZoomIn 0.2", "wait 0.8", "hold UI_Select 1.2", "wait 3.0", "UI_Back", "wait 0.6",
              "UI_Back")


@dataclass
class Command:
    id: str
    action: str                       # the name in Elite's .binds file
    label: str                        # how she refers to it: "the landing gear"
    phrases: Dict[str, List[str]] = field(default_factory=dict)
    doing: Dict[str, str] = field(default_factory=dict)
    flag: Optional[Tuple[str, int, bool]] = None   # (Status.json field, bit, inverted)
    words: Tuple[str, str] = ("on", "off")         # what "on" and "off" mean for "already ..." answers
    strict: bool = False
    echo: Tuple[str, ...] = ()                     # game events this causes (she will not announce them again)
    macro: Tuple[str, ...] = ()                    # several steps instead of one key (see control/macros.py)
    service: Tuple[str, ...] = ()                  # ("voidcompass", overlay id): talks to another app instead of pressing a key

    def do_text(self, intent):
        if intent in self.doing:
            return self.doing[intent]
        return {"on": "Switching on %s", "off": "Switching off %s", "toggle": "Toggling %s",
                "press": "Using %s"}[intent] % self.label


def C(id, action, label, on=None, off=None, toggle=None, press=None, doing=None, flag=None, words=("on", "off"),
      strict=False, macro=(), service=()):
    phrases = {k: v for k, v in (("on", on), ("off", off), ("toggle", toggle), ("press", press)) if v}
    return Command(id, action, label, phrases, doing or {}, flag, words, strict, macro=tuple(macro), service=tuple(service))


CATALOG = [
    # ------------------------------------------------------------------ maps and screens
    C("galaxy_map", "GalaxyMapOpen", "the galaxy map",
      on=["{OPEN_V} [the] galaxy map", "{OPEN_V} [the] galaxy", "galaxy map", "galaxy", "let me see [the] galaxy map", "I want to plot a route",
          "plot [a] (route|course)", "route plotter"],
      off=["{CLOSE_V} [the] galaxy map", "{CLOSE_V} [the] galaxy"],
      toggle=["{TOGGLE_V} [the] galaxy map"],
      doing={"on": "Opening the galaxy map", "off": "Closing the galaxy map", "toggle": "Toggling the galaxy map"}),
    C("system_map", "SystemMapOpen", "the system map",
      on=["{OPEN_V} [the] system map", "system map", "let me see [the] system map", "show [me] [the] system"],
      off=["{CLOSE_V} [the] system map"],
      toggle=["{TOGGLE_V} [the] system map"],
      doing={"on": "Opening the system map", "off": "Closing the system map", "toggle": "Toggling the system map"}),
    C("codex", "OpenCodexGoToDiscovery", "the codex",
      on=["{OPEN_V} [the] codex", "codex", "discovery codex"],
      doing={"on": "Opening the codex"}),
    C("fss_enter", "ExplorationFSSEnter", "the full spectrum scanner",
      on=["{OPEN_V} fss", "(enter|start|use|begin|activate|engage|go into) fss", "fss", "scan the system"],
      off=["{CLOSE_V} fss", "(leave|quit|exit|stop|finish) fss"],
      doing={"on": "Opening the full spectrum scanner", "off": "Closing the full spectrum scanner"}),

    # ------------------------------------------------------------------ ship systems with a known on/off state
    C("gear", "LandingGearToggle", "The landing gear",
      on=["{DEPLOY_V} gear", "gear (down|out|deployed)", "put gear down", "(lower|drop) [the] landing gear",
          "get [the] gear down", "prepare [the] gear", "ready [the] gear", "landing gear down"],
      off=["{RETRACT_V} gear", "gear (up|in|away|retracted)", "put gear up", "get [the] gear (up|in)",
           "gear up please", "landing gear up"],
      toggle=["{TOGGLE_V} gear", "gear toggle", "toggle landing gear", "gear"],
      doing={"on": "Lowering the landing gear", "off": "Raising the landing gear", "toggle": "Toggling the landing gear"},
      flag=("Flags", 2, False), words=("down", "up")),
    C("weapons", "DeployHardpointToggle", "The weapons",
      on=["{DEPLOY_V} weapons", "weapons (out|deployed|up|hot)", "(arm|ready|prepare) weapons", "weapons online",
          "(get|make) weapons ready", "battle stations", "combat ready", "go weapons hot"],
      off=["{RETRACT_V} weapons", "weapons (away|retracted|in|down|safe|cold)", "(stand|stand down) weapons",
           "safe weapons", "stand down", "weapons offline"],
      toggle=["{TOGGLE_V} weapons", "weapons toggle"],
      doing={"on": "Deploying hardpoints", "off": "Retracting hardpoints", "toggle": "Toggling hardpoints"},
      flag=("Flags", 6, False), words=("deployed", "retracted")),
    C("scoop", "ToggleCargoScoop", "The cargo scoop",
      on=["{DEPLOY_V} scoop", "{ON_V} scoop", "scoop (out|open|on|deployed|down)", "(open|extend) [the] scoop"],
      off=["{RETRACT_V} scoop", "{OFF_V} scoop", "scoop (in|up|closed|off|away|retracted)", "(close|retract) [the] scoop"],
      toggle=["{TOGGLE_V} scoop", "scoop toggle", "scoop"],
      doing={"on": "Deploying the cargo scoop", "off": "Retracting the cargo scoop", "toggle": "Toggling the cargo scoop"},
      flag=("Flags", 9, False), words=("deployed", "retracted")),
    C("lights", "ShipSpotLightToggle", "The ship lights",
      on=["{ON_V} lights", "lights (on|up)", "(light|lights) it up", "(let there be|give me) light",
          "(put|get) lights on", "(it is|it's) dark in here"],
      off=["{OFF_V} lights", "lights (off|out)", "(kill|cut) [the] lights", "(put|get) lights off", "(it is|it's) too bright"],
      toggle=["{TOGGLE_V} lights", "lights toggle", "lights"],
      doing={"on": "Lights on", "off": "Lights off", "toggle": "Toggling the lights"},
      flag=("Flags", 8, False)),
    C("night_vision", "NightVisionToggle", "Night vision",
      on=["{ON_V} night vision", "night vision on", "I can't see", "I cannot see"],
      off=["{OFF_V} night vision", "night vision off"],
      toggle=["{TOGGLE_V} night vision", "night vision"],
      doing={"on": "Night vision on", "off": "Night vision off", "toggle": "Toggling night vision"},
      flag=("Flags", 28, False)),
    C("silent_running", "ToggleButtonUpInput", "Silent running",
      on=["{ON_V} silent running", "(go|run) silent", "go dark", "run silent", "silent running on",
          "(rig|set) (for|to) silent running", "stealth", "(go|run) quiet"],
      off=["{OFF_V} silent running", "silent running off", "(stop|end) running silent", "(go|run) loud", "come out of silent running"],
      toggle=["{TOGGLE_V} silent running", "silent running"],
      doing={"on": "Silent running on", "off": "Silent running off", "toggle": "Toggling silent running"},
      flag=("Flags", 10, False)),
    C("flight_assist", "ToggleFlightAssist", "Flight assist",
      on=["{ON_V} flight assist", "flight assist on", "assist on", "(get|put) flight assist back on"],
      off=["{OFF_V} flight assist", "flight assist off", "assist off", "go (manual|dark flight)", "(kill|drop) flight assist"],
      toggle=["{TOGGLE_V} flight assist", "flight assist toggle"],
      doing={"on": "Flight assist on", "off": "Flight assist off", "toggle": "Toggling flight assist"},
      flag=("Flags", 5, True)),
    C("hud_mode", "PlayerHUDModeToggle", "The HUD",
      on=["(switch|change|go) to analysis [mode]", "analysis mode", "{ON_V} analysis mode", "discovery mode", "exploration mode",
          "(switch|change|go) to discovery [mode]"],
      off=["(switch|change|go) to combat [mode]", "combat mode", "{ON_V} combat mode", "fighting mode"],
      toggle=["{TOGGLE_V} (hud|hud mode|cockpit mode)", "(change|swap|switch) hud [mode]", "hud mode"],
      doing={"on": "Switching to analysis mode", "off": "Switching to combat mode", "toggle": "Switching HUD mode"},
      flag=("Flags", 27, False), words=("in analysis mode", "in combat mode")),
    C("head_look", "HeadLookToggle", "Head look",
      on=["{ON_V} head look", "head look on"], off=["{OFF_V} head look", "head look off"],
      toggle=["{TOGGLE_V} head look", "head look"],
      doing={"on": "Head look on", "off": "Head look off", "toggle": "Toggling head look"}),

    # ------------------------------------------------------------------ one-shot actions
    C("heatsink", "DeployHeatSink", "a heat sink",
      press=["{FIRE_V} heatsink", "heatsink", "(dump|vent) heat", "get rid of [the] heat", "(it is|it's) too hot",
             "(cool|cool down) [the] ship", "I need a heatsink"],
      doing={"press": "Deploying a heat sink"}),
    C("shield_cell", "UseShieldCell", "a shield cell",
      press=["{FIRE_V} shield cell", "shield cell", "(recharge|restore|boost|refill) [the] shields", "(I need|give me) (shields|a shield cell)"],
      doing={"press": "Using a shield cell"}),
    C("chaff", "FireChaffLauncher", "chaff",
      press=["{FIRE_V} chaff", "chaff", "(confuse|jam|spoof) [the] (missiles|enemy|hostile)"],
      doing={"press": "Launching chaff"}),
    C("boost", "UseBoostJuice", "the engine boost",
      press=["boost", "(hit|use|engage|fire|activate) [the] (boost|afterburner|afterburners)", "afterburners", "engine boost", "(burn|punch) it",
             "speed boost", "give me a boost"],
      doing={"press": "Boosting"}),
    C("supercruise", "Supercruise", "supercruise",
      press=["supercruise", "(engage|enter|start|go to|jump to|go into|activate) supercruise", "(go|jump) (into|to) supercruise"],
      doing={"press": "Engaging supercruise"}, strict=True),
    C("hyperspace", "Hyperspace", "the hyperspace jump",
      press=["hyperspace", "(engage|start|begin|initiate|activate) hyperspace", "jump to hyperspace", "hyperspace jump",
             "make a hyperspace jump", "engage jump", "{ON_V} jump", "(initiate|begin|start|commence) [the] jump", "jump",
             "make [the] jump", "hit [the] jump", "jump now", "ready to jump"],
      doing={"press": "Engaging hyperspace"}, strict=True),

    # ------------------------------------------------------------------ throttle
    C("speed_0", "SetSpeedZero", "zero throttle",
      press=["(all|full) stop", "stop [the] (ship|engines)", "(throttle|speed) (to )?0", "{SET_V} (throttle|speed|engines) (to )?0",
             "0 (throttle|speed)", "cut [the] (throttle|engines)", "(come to|bring to) a (halt|stop)", "halt", "(kill|stop) [the] throttle"],
      doing={"press": "Stopping the ship"}),
    C("speed_50", "SetSpeed50", "half throttle",
      press=["{SET_V} (throttle|speed|engines) (to )?50", "50 (throttle|speed|power)", "(throttle|speed) 50", "slow (it )?down to 50",
             "half (throttle|speed|power|ahead)"],
      doing={"press": "Setting throttle to fifty percent"}),
    C("speed_75", "SetSpeed75", "three quarter throttle",
      press=["{SET_V} (throttle|speed|engines) (to )?75", "75 (throttle|speed|power)", "(throttle|speed) 75"],
      doing={"press": "Setting throttle to seventy five percent"}),
    C("speed_100", "SetSpeed100", "full throttle",
      press=["{SET_V} (throttle|speed|engines) (to )?100", "100 (throttle|speed|power)", "(throttle|speed) 100", "full (throttle|speed|power|ahead)",
             "max (throttle|speed|power)", "maximum (throttle|speed|power)", "(throttle|speed) (to )?(full|max|maximum)", "ahead full", "flat out"],
      doing={"press": "Full throttle"}),

    # ------------------------------------------------------------------ targeting
    C("next_target", "CycleNextTarget", "the next target",
      press=["{TARGET_V} next [target]", "next target", "cycle (targets|target)", "(change|switch) target", "another target", "(new|different) target"],
      doing={"press": "Next target"}),
    C("prev_target", "CyclePreviousTarget", "the previous target",
      press=["{TARGET_V} previous [target]", "previous target", "cycle (targets|target) (backwards|back)", "(previous|go back to previous) target"],
      doing={"press": "Previous target"}),
    C("next_hostile", "CycleNextHostileTarget", "the next hostile",
      press=["{TARGET_V} next hostile", "next hostile", "{TARGET_V} [a] hostile", "hostile", "{TARGET_V} [the] closest hostile", "(find|get) me [a] hostile",
             "(find|get) [the] next hostile", "cycle hostiles", "who is trying to kill me", "(what is|who is) attacking us", "{TARGET_V} [a] threat"],
      doing={"press": "Targeting next hostile"}),
    C("prev_hostile", "CyclePreviousHostileTarget", "the previous hostile",
      press=["{TARGET_V} previous hostile", "previous hostile", "hostile previous", "cycle hostiles (backwards|back)"],
      doing={"press": "Targeting previous hostile"}),
    C("highest_threat", "SelectHighestThreat", "the highest threat",
      press=["{TARGET_V} [the] highest threat", "highest threat", "(biggest|worst|most dangerous) threat", "(what is|who is) the biggest threat",
             "{TARGET_V} [the] most dangerous (hostile|ship|target)"],
      doing={"press": "Targeting the highest threat"}),
    C("next_route_system", "TargetNextRouteSystem", "the next system on the route",
      press=["{TARGET_V} next system", "next system", "next (jump|waypoint|hop)", "{TARGET_V} next (jump|waypoint)",
             "{TARGET_V} [the] next system on [the] route", "(point|aim|face) [at] [the] next system", "{TARGET_V} [the] route"],
      doing={"press": "Targeting the next system on the route"}),
    C("targets_target", "SelectTargetsTarget", "the target's target",
      press=["{TARGET_V} (its|their|his|her) target", "{TARGET_V} (target's|targets) target", "who is it targeting", "(what|who) is it (shooting|targeting|attacking)"],
      doing={"press": "Targeting its target"}),
    C("next_subsystem", "CycleNextSubsystem", "the next subsystem",
      press=["{TARGET_V} next subsystem", "next subsystem", "(cycle|change) subsystem", "{TARGET_V} [a] subsystem"],
      doing={"press": "Next subsystem"}),
    C("prev_subsystem", "CyclePreviousSubsystem", "the previous subsystem",
      press=["{TARGET_V} previous subsystem", "previous subsystem"],
      doing={"press": "Previous subsystem"}),
    # wingmen: "target wingman 2", "lock wing man two", "wingman 2s" (STT often adds an s or hears "to")
    C("wingman_1", "TargetWingman0", "wingman one",
      press=["{TARGET_V} [my] wingman 1", "wingman 1", "{TARGET_V} [my] wingman number 1", "wingman 1s"],
      doing={"press": "Targeting wingman one"}),
    C("wingman_2", "TargetWingman1", "wingman two",
      press=["{TARGET_V} [my] wingman 2", "wingman 2", "{TARGET_V} [my] wingman number 2", "wingman 2s", "{TARGET_V} [my] wingman to"],
      doing={"press": "Targeting wingman two"}),
    C("wingman_3", "TargetWingman2", "wingman three",
      press=["{TARGET_V} [my] wingman 3", "wingman 3", "{TARGET_V} [my] wingman number 3", "wingman 3s"],
      doing={"press": "Targeting wingman three"}),
    # "assist wingman 2": lock your wingman, then lock whatever THEY are shooting at
    C("assist_1", "TargetWingman0", "wingman one's target",
      press=["assist wingman 1", "assist [my] wingman number 1", "{TARGET_V} wingman (1|1s|1 s) target", "wingman (1|1s|1 s) target",
             "what is wingman 1 (targeting|shooting|attacking)"],
      doing={"press": "Targeting what wingman one is shooting"}, macro=("TargetWingman0", "wait 0.4", "SelectTargetsTarget")),
    C("assist_2", "TargetWingman1", "wingman two's target",
      press=["assist wingman 2", "assist [my] wingman number 2", "{TARGET_V} wingman (2|2s|2 s) target", "wingman (2|2s|2 s) target",
             "what is wingman 2 (targeting|shooting|attacking)", "assist wingman to"],
      doing={"press": "Targeting what wingman two is shooting"}, macro=("TargetWingman1", "wait 0.4", "SelectTargetsTarget")),
    C("assist_3", "TargetWingman2", "wingman three's target",
      press=["assist wingman 3", "assist [my] wingman number 3", "{TARGET_V} wingman (3|3s|3 s) target", "wingman (3|3s|3 s) target",
             "what is wingman 3 (targeting|shooting|attacking)"],
      doing={"press": "Targeting what wingman three is shooting"}, macro=("TargetWingman2", "wait 0.4", "SelectTargetsTarget")),
    C("wing_nav_lock", "WingNavLock", "wing nav lock",
      press=["wing nav lock", "nav lock", "(lock|follow) (on to )?wingman", "follow wingman"],
      doing={"press": "Wing nav lock"}),
    C("next_fire_group", "CycleFireGroupNext", "the next fire group",
      press=["next fire group", "(switch|cycle|change|go to) [the] next fire group", "(switch|change|cycle) fire group",
             "(switch|change) weapons group", "next group"],
      doing={"press": "Next fire group"}),
    C("prev_fire_group", "CycleFireGroupPrevious", "the previous fire group",
      press=["previous fire group", "(switch|cycle|change|go to) [the] previous fire group", "previous group"],
      doing={"press": "Previous fire group"}),

    # ------------------------------------------------------------------ more combat (ship)
    C("ecm", "ChargeECM", "the ECM",
      press=["{FIRE_V} ecm", "ecm", "charge [the] ecm", "(shock|blast) [the] missiles", "electronic countermeasures"],
      doing={"press": "Charging the ECM"}),
    C("power_engines", "IncreaseEnginesPower", "power to engines",
      press=["(power|more power|pips|send power|divert power|increase power) (to )?engines", "engines (power|pips)", "pips to engines",
             "(power|boost) engines"],
      doing={"press": "More power to engines"}),
    C("power_weapons", "IncreaseWeaponsPower", "power to weapons",
      press=["(power|more power|pips|send power|divert power|increase power) (to )?weapons", "weapons (power|pips)", "pips to weapons",
             "(power|boost) weapons"],
      doing={"press": "More power to weapons"}),
    C("power_systems", "IncreaseSystemsPower", "power to systems",
      press=["(power|more power|pips|send power|divert power|increase power) (to )?systems", "systems (power|pips)",
             "pips to systems", "(power|boost) systems"],
      doing={"press": "More power to systems"}),
    C("power_reset", "ResetPowerDistribution", "balanced power",
      press=["(reset|balance|even out|equalise|equalize) (the )?(power|pips)", "balanced power", "power (reset|balance)", "reset pips"],
      doing={"press": "Balancing power"}),

    # ------------------------------------------------------------------ ship-launched fighter orders
    C("fighter_orders", "OpenOrders", "the fighter orders",
      press=["{OPEN_V} [the] (fighter|crew) orders", "(fighter|crew) orders", "orders menu"],
      doing={"press": "Opening the orders menu"}),
    C("fighter_attack", "OrderFocusTarget", "attack my target",
      press=["(fighter|crew) attack [my] target", "attack my target", "(fighter|crew) focus (on )?[my] target", "focus fire", "(fighter|crew) attack"],
      doing={"press": "Ordering the fighter to attack my target"}),
    C("fighter_defend", "OrderDefensiveBehaviour", "defensive behaviour",
      press=["(fighter|crew) defend", "(fighter|crew) defensive", "defend me", "(fighter|crew) protect me"],
      doing={"press": "Fighter on defence"}),
    C("fighter_aggressive", "OrderAggressiveBehaviour", "aggressive behaviour",
      press=["(fighter|crew) aggressive", "(fighter|crew) (go|be) aggressive", "(fighter|crew) free for all"],
      doing={"press": "Fighter on aggressive"}),
    C("fighter_hold_fire", "OrderHoldFire", "hold fire",
      press=["(fighter|crew) hold fire", "(fighter|crew) cease fire", "(fighter|crew) stop shooting"],
      doing={"press": "Fighter holding fire"}),
    C("fighter_hold_position", "OrderHoldPosition", "hold position",
      press=["(fighter|crew) hold position", "(fighter|crew) hold", "(fighter|crew) stay (there|put)"],
      doing={"press": "Fighter holding position"}),
    C("fighter_follow", "OrderFollow", "follow me",
      press=["(fighter|crew) follow [me]", "(fighter|crew) form up", "(fighter|crew) on me"],
      doing={"press": "Fighter following"}),
    C("fighter_recall", "OrderRequestDock", "recall the fighter",
      press=["(fighter|crew) (come back|return|dock|recall)", "recall [the] fighter", "(bring|call) [the] fighter back"],
      doing={"press": "Recalling the fighter"}),

    # ------------------------------------------------------------------ on foot (needs these keys set in Elite's on-foot controls)
    C("foot_primary", "HumanoidSelectPrimaryWeaponButton", "the primary weapon",
      press=["(draw|equip|select|switch to|pull out|get) [my] (primary|main) weapon", "primary weapon", "(draw|equip) [my] rifle"],
      doing={"press": "Drawing the primary weapon"}),
    C("foot_secondary", "HumanoidSelectSecondaryWeaponButton", "the secondary weapon",
      press=["(draw|equip|select|switch to|pull out|get) [my] (secondary|side) weapon", "secondary weapon", "(draw|equip) [my] (pistol|sidearm)"],
      doing={"press": "Drawing the secondary weapon"}),
    C("foot_holster", "HumanoidHideWeaponButton", "holstering the weapon",
      press=["holster", "(holster|sheathe) [my] (rifle|pistol|sidearm)"],
      doing={"press": "Holstering the weapon"}),
    C("foot_reload", "HumanoidReloadButton", "reloading",
      press=["reload", "reload [my] weapon", "(I need to|let me) reload"],
      doing={"press": "Reloading"}),
    C("foot_melee", "HumanoidMeleeButton", "a melee attack",
      press=["melee", "melee attack", "(hit|bash) (him|them)"],
      doing={"press": "Melee"}),

    # ------------------------------------------------------------------ macros (no single key in Elite)
    C("request_docking", "FocusLeftPanel", "the docking request",
      press=["request docking", "requesting (docking|landing) [(permission|clearance)]", "requesting permission to (dock|land)", "{REQUEST_V} (docking|landing) [(permission|clearance|request)]",
             "(ask|call|contact) [the] (station|port|control|tower|traffic control) for (docking|landing) (permission|clearance|request)",
             "(ask|call|contact) [the] (station|port|control|tower) for (docking|landing)",
             "request permission to (dock|land)", "permission to (dock|land)", "(send|make|open) [a] (docking|landing) request",
             "docking request", "can I (dock|land)", "request (a )?(dock|landing)", "request station docking", "dock request",
             "ask for (docking|landing)"],
      doing={"press": "Requesting docking"}, strict=True, macro=DOCKING_MACRO),
    C("deploy_nomad", "FocusRadarPanel", "the Nomad",
      press=["(deploy|launch|send out|release|drop|put out) [the|my] nomad", "nomad (deploy|launch)", "(deploy|launch) [the|my] (nomad shuttle|exploration shuttle)",
             "get the nomad out", "(deploy|launch) nomad"],
      doing={"press": "Deploying the Nomad"}, strict=True, macro=NOMAD_MACRO),

    C("auto_launch", "UI_Select", "the launch",
      press=["launch", "auto launch", "[(please|ok)] launch (the ship|us|now)", "(launch|take off|lift off|depart) (from|out of|off) [the] (station|port|pad|dock|starport|outpost)",
             "(auto|automatic) (launch|take off)", "{REQUEST_V} (launch|take off)", "undock", "(undock|launch) [the] ship", "take off", "launch us",
             "[(number one|number 1|number|one|ok|okay|alright|right|computer|starling)] (take|get|bring) (us|her|the ship) (out|off|away|underway)",
             "(take|get|bring) (us|her|the ship) out of (here|the station|the dock|the port|the hangar)",
             "(you|starling) (have|has) (control|the (helm|conn|con|ship|controls|wheel))", "you've got (control|the (helm|conn|ship|controls))",
             "(the )?(ship|helm|conn|controls) (is|are) yours", "take (control|the helm|the conn|the controls)",
             "(take|make) (it|us) (out|away) (please|now)", "(engage|begin|start) (the )?(launch|undock|undocking)( sequence)?",
             "(let's|lets) get out of here", "(launch|undock|take off) (please|now)"],
      doing={"press": "Launching"}, strict=True, macro=LAUNCH_MACRO),

    C("plot_waypoint", "GalaxyMapOpen", "the next waypoint",
      press=["(plot|set|put in|enter|load|lay in) [the] (next|neutron) (waypoint|stop|neutron|neutron star)",
             "(plot|set) [the] waypoint", "(plot|set) [the] next (waypoint|stop) [in] [the] (galaxy map|nav|navigation)",
             "(plot|set) [the] route [to] [the] next (waypoint|stop)", "next waypoint in [the] galaxy map"],
      doing={"press": "Plotting the next waypoint"}, strict=True, macro=PLOT_MACRO),

    # ------------------------------------------------------------------ cockpit panels and radar
    C("left_panel", "FocusLeftPanel", "the left panel",
      press=["{OPEN_V} [the] (left|target|navigation|nav|contacts) panel", "(left|target|navigation|nav|contacts) panel",
             "(show|open) contacts", "(show|open) navigation", "navigation panel"],
      doing={"press": "Opening the left panel"}),
    C("comms_panel", "FocusCommsPanel", "the comms panel",
      press=["{OPEN_V} [the] (comms|chat|messages|communications) panel", "(comms|chat|communications) panel", "{OPEN_V} comms",
             "check (messages|comms)", "(any|new) messages"],
      doing={"press": "Opening the comms panel"}),
    C("radar_panel", "FocusRadarPanel", "the role panel",
      press=["{OPEN_V} [the] (radar|role|scanner) panel", "(radar|role) panel", "{OPEN_V} [the] radar", "{OPEN_V} (role|ship role) panel"],
      doing={"press": "Opening the role panel"}),
    C("right_panel", "FocusRightPanel", "the right panel",
      press=["{OPEN_V} [the] (right|systems|internal|functions|status) panel", "(right|systems|internal|status) panel", "{OPEN_V} (ship )?status",
             "{OPEN_V} [the] modules"],
      doing={"press": "Opening the right panel"}),
    C("radar_range_up", "RadarIncreaseRange", "radar range",
      press=["(increase|extend|raise|expand|widen|zoom out) [the] radar [range]", "radar (range )?(up|out|bigger|longer)", "zoom radar out"],
      doing={"press": "Increasing radar range"}),
    C("radar_range_down", "RadarDecreaseRange", "radar range",
      press=["(decrease|reduce|lower|shrink|narrow|zoom in) [the] radar [range]", "radar (range )?(down|in|smaller|shorter)", "zoom radar in"],
      doing={"press": "Decreasing radar range"}),
    C("orbit_lines", "OrbitLinesToggle", "orbit lines",
      press=["{TOGGLE_V} orbit lines", "(show|hide|turn on|turn off) orbit lines", "orbit lines"],
      doing={"press": "Toggling orbit lines"}),
]


# ---------------------------------------------------------------------- Void Compass overlays (one command each)
def overlay_command(overlay_id, label, names, needs_word):
    """One on/off/toggle command for a Void Compass overlay."""
    if True:
        tail = "(overlay|hud)" if needs_word else "[overlay] [hud]"
        said = "(%s)" % "|".join(names)
        command = C(
            "vc_" + overlay_id.replace("-", "_"), "", label,
            on=["{OPEN_V} [the] %s %s" % (said, tail), "{ON_V} [the] %s %s" % (said, tail), "%s %s on" % (said, tail)],
            off=["{CLOSE_V} [the] %s %s" % (said, tail), "{OFF_V} [the] %s %s" % (said, tail), "%s %s off" % (said, tail)],
            toggle=["{TOGGLE_V} [the] %s %s" % (said, tail)],
            doing={"on": "Switching on " + label, "off": "Switching off " + label, "toggle": "Toggling " + label},
            words=("on", "off"), service=("voidcompass", overlay_id))
    return command


def _overlay_commands():
    from control.vc_overlays import HIDE_ALL, OVERLAYS, SHOW_ALL
    commands = [overlay_command(*row) for row in OVERLAYS]
    commands.append(C(
        "vc_hide_all", "", "the overlays",
        press=["(hide|clear|remove|dismiss|close|get rid of|turn off|switch off|disable|kill) [every|all] overlays",
               "overlays (off|away|hidden|out of the way)", "(hide|clear) [the] screen"],
        doing={"press": "Hiding the overlays"}, service=("voidcompass", HIDE_ALL)))
    commands.append(C(
        "vc_show_all", "", "the overlays",
        press=["(show|bring back|restore|unhide|display|turn on|switch on|enable|bring up) [every|all] overlays",
               "overlays (on|back|visible)"],
        doing={"press": "Bringing the overlays back"}, service=("voidcompass", SHOW_ALL)))
    return commands


CATALOG.extend(_overlay_commands())

# Game events each command causes. After she does it, she does not announce these again.
ECHO = {
    "galaxy_map": ("GalaxyMapOpened", "ScreenClosed"),
    "system_map": ("SystemMapOpened", "OrreryOpened", "ScreenClosed"),
    "codex": ("CodexOpened", "ScreenClosed"),
    "fss_enter": ("FssOpened", "ScreenClosed"),
    "gear": ("LandingGearDown", "LandingGearUp"),
    "weapons": ("HardpointsDeployed", "HardpointsRetracted"),
    "scoop": ("CargoScoopDeployed", "CargoScoopRetracted"),
    "lights": ("LightsOn", "LightsOff"),
    "night_vision": ("NightVisionOn", "NightVisionOff"),
    "silent_running": ("SilentRunningOn", "SilentRunningOff"),
    "flight_assist": ("FlightAssistOn", "FlightAssistOff"),
    "hud_mode": ("AnalysisModeOn", "CombatModeOn"),
    "supercruise": ("FsdCharging", "SupercruiseEntry", "SupercruiseExit"),
    "hyperspace": ("FsdCharging", "StartJump"),
    "left_panel": ("ExternalPanelOpened", "ScreenClosed"),
    "comms_panel": ("CommsPanelOpened", "ScreenClosed"),
    "radar_panel": ("RolePanelOpened", "ScreenClosed"),
    "right_panel": ("InternalPanelOpened", "ScreenClosed"),
}
for _command in CATALOG:
    _command.echo = ECHO.get(_command.id, ())


def by_id(command_id):
    for command in CATALOG:
        if command.id == command_id:
            return command
    return None
