import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from control.matcher import Matcher
from core import paths
from core.event_bus import Event, EventBus
from core.settings import Settings
from personality import line_keys
from personality.dialogue import DialogueManager
from personality.speaker import EventSpeaker, load_rules
from tests.helpers import make_processor
from tests.test_mood import MoodBase
from tests.test_dialogue import FakeSpeech


def ev(name, **data):
    return SimpleNamespace(name=name, data=data, priority="normal")


class ShipChangeTests(unittest.TestCase):
    def setUp(self):
        self.processor, self.bus, self.heard = make_processor()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(Path(self.tmp.name) / "s.json").load()
        self.speech = FakeSpeech()
        dialogue = DialogueManager(paths.VOICEPACKS_DIR / "default", [paths.DIALOGUE_DIR / "core_lines.json"]).load()
        EventSpeaker(self.bus, self.speech, dialogue, self.settings, load_rules()).attach()

    def test_swapping_ship_is_announced_by_name(self):
        self.processor.handle_line(json.dumps({"event": "ShipyardSwap", "ShipType": "python", "ShipType_Localised": "Python", "ShipID": 5}))
        self.assertEqual(len(self.speech.said), 1)
        self.assertIn("Python", self.speech.said[0]["text"])
        self.assertEqual(self.processor.state.ship, "python")

    def test_lowercase_name_is_tidied(self):
        self.processor.handle_line(json.dumps({"event": "ShipyardSwap", "ShipType": "federation_dropship"}))
        self.assertIn("Federal Dropship", self.speech.said[0]["text"])


class KeyTests(unittest.TestCase):
    def test_only_wanted_targets_are_spoken(self):
        self.assertEqual(line_keys.keys_for(ev("ShipTargeted", LegalStatus="Wanted")), ["ShipTargeted_Wanted"])
        self.assertEqual(line_keys.keys_for(ev("ShipTargeted", LegalStatus="Clean")), [])

    def test_interdiction_result(self):
        self.assertEqual(line_keys.keys_for(ev("Interdiction", Success=True)), ["Interdiction_Success"])
        self.assertEqual(line_keys.keys_for(ev("Interdiction", Success=False)), ["Interdiction_Failed"])

    def test_on_foot_lines_come_first(self):
        keys = line_keys.keys_for(ev("FactionKillBond", OnFoot=True))
        self.assertEqual(keys, ["Bounty_OnFoot", "Bounty"])
        self.assertEqual(line_keys.keys_for(ev("UnderAttack", OnFoot=False)), ["UnderAttack"])

    def test_every_new_key_has_lines(self):
        dialogue = DialogueManager(paths.VOICEPACKS_DIR / "default", [paths.DIALOGUE_DIR / "core_lines.json"]).load()
        for key in ("ShipyardSwap", "WingAdd", "WingJoined", "WingLeft", "WingInvite", "ShipTargeted_Wanted", "Interdiction_Success",
                    "Interdiction_Failed", "PVPKill", "Bounty_OnFoot", "UnderAttack_OnFoot", "Died_OnFoot", "React_WantedKill"):
            self.assertIsNotNone(dialogue.pick(key, "", False, False), key)


class OnFootTagTests(unittest.TestCase):
    def test_on_foot_flag_comes_from_status(self):
        processor, bus, heard = make_processor()
        processor.state.status_flags2 = 1
        processor.handle_line(json.dumps({"event": "Bounty", "TotalReward": 5000, "VictimFaction": "X"}))
        self.assertTrue(heard[-1].data["OnFoot"])
        processor.state.status_flags2 = 0
        processor.handle_line(json.dumps({"event": "Bounty", "TotalReward": 5000, "VictimFaction": "X"}))
        self.assertFalse(heard[-1].data["OnFoot"])


class CombatMoodTests(MoodBase):
    def test_dying_in_a_fight_costs_nothing(self):
        self.send("UnderAttack", {"Target": "You"}, "critical")
        before = self.engine.score
        self.send("Died", {"KillerName": "Pirate"}, "critical")
        self.assertEqual(self.engine.score, before)

    def test_dying_with_a_killer_but_no_warning_costs_nothing(self):
        self.send("Died", {"KillerName": "Pirate"}, "critical")
        self.assertEqual(self.engine.score, 0)

    def test_wing_death_costs_nothing(self):
        self.send("Died", {"Killers": [{"KillerName": "A"}, {"KillerName": "B"}]}, "critical")
        self.assertEqual(self.engine.score, 0)

    def test_dying_for_no_reason_still_costs(self):
        self.send("Died", {}, "critical")
        self.assertLess(self.engine.score, 0)

    def test_killing_wanted_ships_cheers_her_up(self):
        self.send("Bounty", {"TotalReward": 50000})
        self.assertGreaterEqual(self.engine.score, 2)

    def test_a_big_bounty_is_worth_more(self):
        self.send("Bounty", {"TotalReward": 3_000_000})
        self.assertGreaterEqual(self.engine.score, 4)

    def test_combat_bonds_and_pvp_kills(self):
        self.send("FactionKillBond", {"Reward": 1000})
        self.send("CapShipBond", {"Reward": 1000})
        self.send("PVPKill", {"Victim": "X"})
        self.assertGreater(self.engine.score, 3)

    def test_a_kill_counts_as_being_in_a_fight(self):
        self.send("PVPKill", {"Victim": "X"})
        before = self.engine.score
        self.send("HullDamage", {"Fighter": False, "PlayerPilot": True}, "critical")
        self.assertEqual(self.engine.score, before)


class CombatCommandTests(unittest.TestCase):
    def setUp(self):
        self.m = Matcher()

    def ids(self, text):
        match = self.m.match(text)
        return match.command.id if match else None

    def test_target_wingmen(self):
        for text, expected in (("target wingman 2", "wingman_2"), ("target wingman two", "wingman_2"), ("target wing man one", "wingman_1"),
                               ("lock wingmate 3", "wingman_3"), ("wingman 2s", "wingman_2"), ("target my wingman to", "wingman_2")):
            self.assertEqual(self.ids(text), expected, text)

    def test_assist_wingman_is_a_two_step_macro(self):
        match = self.m.match("assist wingman 2")
        self.assertEqual(match.command.id, "assist_2")
        self.assertEqual(match.command.macro, ("TargetWingman1", "wait 0.4", "SelectTargetsTarget"))
        self.assertEqual(self.ids("target wingman 2s target"), "assist_2")

    def test_other_combat_commands(self):
        for text, expected in (("charge the ecm", "ecm"), ("power to engines", "power_engines"), ("pips to weapons", "power_weapons"),
                               ("reset the pips", "power_reset"), ("fighter attack my target", "fighter_attack"),
                               ("recall the fighter", "fighter_recall"), ("reload", "foot_reload"),
                               ("draw my primary weapon", "foot_primary")):
            self.assertEqual(self.ids(text), expected, text)


if __name__ == "__main__":
    unittest.main()
