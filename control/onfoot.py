"""
On-foot voice commands: everything in Elite's on-foot (Humanoid) controls that a key can do.

The commands are plain catalog entries (control/catalog.py has no on-foot code of its own beyond one line that calls
on_foot_commands() below). Emote words ("wave", "dance"...) come from config/emotes.json so you can match them to
your own emote wheel without touching code.
"""

import json

from core import paths
from core.logger import get_logger

log = get_logger("onfoot")


def _load_emotes(path=None):
    try:
        with open(path or (paths.CONFIG_DIR / "emotes.json"), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    out = {}
    for word, slot in data.items():
        if word.startswith("_") or not isinstance(slot, int) or not 1 <= slot <= 8:
            continue
        out[str(word).strip().lower()] = slot
    return out


def on_foot_commands(C, emotes=None):
    """Builds the catalog entries. C is the catalog's own C(...) helper."""
    cmds = [
        C("foot_shields", "HumanoidToggleShieldsButton", "the suit shields",
          press=["(suit|personal|foot) shields", "(raise|lower|toggle|flip|switch) [my] (suit|personal) shields",
                 "shields (up|down) on foot", "(suit|personal) shields (up|down|on|off)"],
          doing={"press": "Toggling the suit shields"}),
        C("foot_torch", "HumanoidToggleFlashlightButton", "the torch",
          press=["(torch|flashlight)", "[turn] (torch|flashlight) (on|off)", "(toggle|switch|flip) [the|my] (torch|flashlight)",
                 "(lights|light) on foot", "(turn on|turn off|switch on|switch off) [the|my] (torch|flashlight)"],
          doing={"press": "Toggling the torch"}),
        C("foot_night_vision", "HumanoidToggleNightVisionButton", "the visor night vision",
          press=["(helmet|visor|suit|foot) night vision", "(toggle|switch|turn on|turn off) (helmet|visor|suit) night vision"],
          doing={"press": "Toggling night vision"}),
        C("foot_health", "HumanoidHealthPack", "a medical pack",
          press=["(use|take|give me|apply|I need) [a|my] (health|medical|med) (pack|kit)", "(heal|heal me|medic)", "(health|medical) pack", "med kit"],
          doing={"press": "Using a medical pack"}),
        C("foot_battery", "HumanoidBattery", "an energy cell",
          press=["(use|take|give me|put in|swap in|I need) [an|a|my] (battery|energy cell|power cell|battery pack)", "(battery|energy cell|power cell|battery pack)"],
          doing={"press": "Using an energy cell"}),
        C("foot_grenade_throw", "HumanoidThrowGrenadeButton", "a grenade",
          press=["(throw|toss|lob|chuck) [a|the|my] grenade", "grenade", "frag out", "grenade out"],
          doing={"press": "Throwing a grenade"}, strict=True),
        C("foot_grenade_next", "HumanoidSelectNextGrenadeTypeButton", "the next grenade type",
          press=["next grenade [type]", "(change|switch|cycle) [the] grenade [type]", "(change|switch|cycle) grenades"],
          doing={"press": "Next grenade type"}),
        C("foot_grenade_prev", "HumanoidSelectPreviousGrenadeTypeButton", "the previous grenade type",
          press=["previous grenade [type]", "last grenade [type]", "(go back to|back to) [the] (last|previous) grenade"],
          doing={"press": "Previous grenade type"}),
        C("foot_grenade_frag", "HumanoidSelectFragGrenade", "frag grenades",
          press=["(select|equip|switch to|use|get|pick) [the|my] (frag|fragmentation|explosive) grenades?", "frag grenades?"],
          doing={"press": "Frag grenades selected"}),
        C("foot_grenade_emp", "HumanoidSelectEMPGrenade", "EMP grenades",
          press=["(select|equip|switch to|use|get|pick) [the|my] (EMP|E M P|electromagnetic) grenades?", "(EMP|E M P) grenades?"],
          doing={"press": "EMP grenades selected"}),
        C("foot_grenade_shield", "HumanoidSelectShieldGrenade", "shield grenades",
          press=["(select|equip|switch to|use|get|pick) [the|my] (shield|shielding) grenades?", "(shield|shielding) grenades?"],
          doing={"press": "Shield grenades selected"}),
        C("foot_next_weapon", "HumanoidSelectNextWeaponButton", "the next weapon",
          press=["next (gun|weapon)", "cycle [my] (gun|guns)"], doing={"press": "Next weapon"}),
        C("foot_prev_weapon", "HumanoidSelectPreviousWeaponButton", "the previous weapon",
          press=["previous weapon", "last weapon"], doing={"press": "Previous weapon"}),
        C("foot_utility", "HumanoidSelectUtilityWeaponButton", "the utility slot",
          press=["(draw|equip|select|switch to|pull out|get) [my] (utility|gadget) [(slot|weapon|item)]", "utility (slot|weapon)"],
          doing={"press": "Utility slot"}),
        C("foot_switch_weapon", "HumanoidSwitchWeapon", "the weapon swap",
          press=["(switch|swap) to the other (gun|weapon)", "other (gun|weapon)"], doing={"press": "Swapping weapon"}),
        C("foot_recharge_tool", "HumanoidSwitchToRechargeTool", "the energy link",
          press=["(equip|select|switch to|get|pull out|use) [the|my] (energy link|recharge tool|recharger)", "(energy link|recharge tool)"],
          doing={"press": "Energy link"}),
        C("foot_comp_analyser", "HumanoidSwitchToCompAnalyser", "the composition scanner",
          press=["(equip|select|switch to|get|pull out|use) [the|my] (composition scanner|comp analyser|compound scanner|analyser|analyzer)", "composition scanner"],
          doing={"press": "Composition scanner"}),
        C("foot_suit_tool", "HumanoidSwitchToSuitTool", "the profile analyser",
          press=["(equip|select|switch to|get|pull out|use) [the|my] (suit tool|profile analyser|profile analyzer|genetic sampler|genetic scanner)", "(suit tool|profile analyser)"],
          doing={"press": "Suit tool"}),
        C("foot_tool_mode", "HumanoidToggleToolModeButton", "the tool mode",
          press=["(toggle|change|switch|flip) [the] tool mode", "tool mode"], doing={"press": "Changing the tool mode"}),
        C("foot_interact", "HumanoidPrimaryInteractButton", "interact",
          press=["(interact|use it|activate it|press the button|open it|open the door)", "primary interact"], doing={"press": "Interacting"}),
        C("foot_interact2", "HumanoidSecondaryInteractButton", "the secondary interact",
          press=["secondary interact", "interact (again|twice|two)"], doing={"press": "Secondary interact"}),
        C("foot_jump", "HumanoidJumpButton", "a jump",
          press=["hop", "(jump|hop) (up|over)", "(on foot|suit) jump", "jump over (it|that)"], doing={"press": "Jump"}),
        C("foot_crouch", "HumanoidCrouchButton", "crouching",
          press=["(crouch|duck|get down|take cover)", "(toggle|stand up from) crouch"], doing={"press": "Crouching"}),
        C("foot_sprint", "HumanoidSprintButton", "sprinting",
          press=["(sprint|run|run for it|run away)"], doing={"press": "Sprinting"}),
        C("foot_walk", "HumanoidWalkButton", "walking",
          press=["(walk|slow down|walking pace)", "toggle walk"], doing={"press": "Walking"}),
        C("foot_zoom", "HumanoidZoomButton", "aiming down the sights",
          press=["(aim|zoom|aim down sights|down sights|aim down the sights)"], doing={"press": "Aiming"}),
        C("foot_item_wheel", "HumanoidItemWheelButton", "the item wheel",
          press=["(open|show|bring up) [the] (item wheel|inventory wheel)", "item wheel"], doing={"press": "Item wheel"}),
        C("foot_emote_wheel", "HumanoidEmoteWheelButton", "the emote wheel",
          press=["(open|show|bring up) [the] emote wheel", "emote wheel", "emotes"], doing={"press": "Emote wheel"}),
        C("foot_ping", "HumanoidPing", "a ping",
          press=["ping", "(mark|ping) (that|this|it)", "mark (that|this|target)"], doing={"press": "Pinging"}),
        C("foot_mission_help", "HumanoidToggleMissionHelpPanelButton", "the mission help panel",
          press=["(mission help|objective help) [panel]", "(show|hide|toggle) [the] mission help"], doing={"press": "Mission help"}),
        C("foot_comms", "HumanoidOpenAccessPanelButton", "the access panel",
          press=["(open|show) [the] access panel", "access panel"], doing={"press": "Access panel"}),
    ]
    for word, slot in (emotes if emotes is not None else _load_emotes()).items():
        key = word.replace(" ", "_")
        cmds.append(C("foot_emote_" + key, "HumanoidEmoteSlot%d" % slot, "the %s emote" % word,
                      press=[word, "(do|play|perform|give|make) [a|an|the] %s" % word, "%s (emote|please)" % word,
                             "emote %s" % word],
                      doing={"press": word.capitalize()}))
    return cmds
