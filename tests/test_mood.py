import json
import tempfile
import unittest
from pathlib import Path

from core import paths
from core.event_bus import EventBus
from core.settings import Settings
from personality.dialogue import DialogueManager
from personality.mood_engine import MoodEngine, effective_mood, matches
from tests.helpers import make_processor


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t

    def wait(self, minutes):
        self.t += minutes * 60


class MoodBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.bus = EventBus()
        self.settings = Settings(Path(self.tmp.name) / "s.json").load()
        self.said = []
        self.dialogue = DialogueManager(paths.VOICEPACKS_DIR / "default").load()
        self.engine = MoodEngine(self.bus, self.settings, save_path=Path(self.tmp.name) / "mood.json",
                                 dialogue=self.dialogue, speak=self.said.append, clock=self.clock)
        self.engine.attach()

    def tearDown(self):
        self.tmp.cleanup()

    def send(self, name, data=None, priority="normal"):
        self.bus.publish(name, data or {}, priority)


class ConditionTests(unittest.TestCase):
    def test_conditions(self):
        d = {"Type": "ImperialSlaves", "BlackMarket": True, "Complete": False}
        self.assertTrue(matches({"field": "Type", "contains": "slave"}, d, {}))
        self.assertTrue(matches({"any": [{"field": "Nope", "is": True}, {"field": "BlackMarket", "is": True}]}, d, {}))
        self.assertFalse(matches({"all": [{"field": "BlackMarket", "is": True}, {"field": "Complete", "is": True}]}, d, {}))
        self.assertTrue(matches({"ctx": "not_in_combat"}, d, {"not_in_combat": True}))
        self.assertFalse(matches({"field": "Missing", "equals": 1}, d, {}))
        self.assertTrue(matches(None, d, {}))


class MoodTests(MoodBase):
    def test_slaves_make_her_unhappy(self):
        self.send("MarketSell", {"Type": "slaves"}, "low")
        self.assertLess(self.engine.score, 0)

    def test_repeating_gives_less_and_less(self):
        gains = []
        for _ in range(8):
            before = self.engine.score
            self.send("MarketSell", {"Type": "slaves"}, "low")
            gains.append(before - self.engine.score)
        self.assertTrue(all(a > b for a, b in zip(gains, gains[1:])))
        self.assertLess(sum(gains), 4 * 2.6)       # base 4 can never add up to more than 2.5x
        self.assertEqual(self.engine.band, "Neutral")

    def test_fatigue_recovers_after_quiet_time(self):
        self.send("MarketSell", {"Type": "slaves"}, "low")
        first = -self.engine.score
        for _ in range(4):
            self.send("MarketSell", {"Type": "slaves"}, "low")
        self.clock.wait(60)
        self.engine.reset()
        self.send("MarketSell", {"Type": "slaves"}, "low")
        self.assertAlmostEqual(-self.engine.score, first, places=1)

    def test_hourly_cap(self):
        for category_event in ("Died", "SelfDestruct", "MissionFailed", "MissionAbandoned", "HeatDamage", "JetConeDamage"):
            for _ in range(5):
                self.send(category_event, {}, "normal")
        for crime in ("murder", "piracy", "assault"):
            self.send("CommitCrime", {"CrimeType": crime})
        self.send("MarketSell", {"Type": "slaves"}, "low")
        self.assertGreaterEqual(self.engine.score, -15.01)

    def test_one_big_mistake_does_not_change_mood(self):
        self.send("CommitCrime", {"CrimeType": "murder"})
        self.assertEqual(self.engine.band, "Neutral")
        self.assertLess(self.engine.score, -4)

    def test_shields_only_matter_outside_combat(self):
        self.send("CombatModeOn")
        self.send("ShieldState", {"ShieldsUp": False}, "critical")
        self.assertEqual(self.engine.score, 0)
        self.send("AnalysisModeOn")
        self.clock.wait(5)
        self.send("ShieldState", {"ShieldsUp": False}, "critical")
        self.assertLess(self.engine.score, 0)

    def test_recent_attack_counts_as_combat(self):
        self.send("UnderAttack", {"Target": "x"}, "critical")
        self.send("ShieldState", {"ShieldsUp": False}, "critical")
        self.assertEqual(self.engine.score, 0)

    def test_hardpoints_count_as_combat(self):
        self.send("HardpointsDeployed")
        self.send("HullDamage", {"Health": 0.8, "Fighter": False, "PlayerPilot": True}, "critical")
        self.assertEqual(self.engine.score, 0)

    def test_sales_scale_with_amount(self):
        self.send("SellExplorationData", {"TotalEarnings": 50_000})
        self.assertEqual(self.engine.score, 0)
        self.send("SellExplorationData", {"TotalEarnings": 12_000_000})
        self.assertGreater(self.engine.score, 1.5)

    def test_she_calms_down_over_time(self):
        self.send("CommitCrime", {"CrimeType": "murder"})
        before = self.engine.score
        self.clock.wait(60)
        self.engine.refresh()
        self.assertGreater(self.engine.score, before)

    def test_going_afk_does_not_cost_points(self):
        self.engine.score = 40
        self.send("Docked", {})                              # the last thing that happened in the game
        self.clock.wait(3 * 3600)                            # three hours away from the keyboard
        self.engine.refresh()
        self.assertGreater(self.engine.score, 39.5)          # at most the 5 minutes after the last event can calm her

    def test_nothing_calms_before_any_game_event(self):
        self.engine.score = 40
        self.clock.wait(2 * 3600)
        self.engine.refresh()
        self.assertEqual(self.engine.score, 40)

    def test_moods_switch_up_at_the_line_and_fall_back_four_points_below_it(self):
        self.engine.score = 29
        self.engine.refresh()
        self.assertEqual(self.engine.band, "Friendly")
        self.engine.score = 30
        self.engine.refresh()
        self.assertEqual(self.engine.band, "Close")         # no extra points needed to move up
        self.engine.score = 28
        self.engine.refresh()
        self.assertEqual(self.engine.band, "Close")         # stays Close until she is below 26
        self.engine.score = 25
        self.engine.refresh()
        self.assertEqual(self.engine.band, "Friendly")

    def test_every_mood_switches_live_the_same_way_a_restart_would_choose_it(self):
        """Climbing slowly through every score gives the same mood as starting fresh at that score (what a restart does)."""
        self.engine.score = -100
        self.engine.band = None
        self.engine.refresh()
        for tenths in range(-1000, 1001, 5):
            self.engine.score = tenths / 10.0
            self.engine.refresh()
            fresh = self.engine._band_for(self.engine.score, None)
            self.assertEqual(self.engine.band, fresh, self.engine.score)
        self.assertEqual(self.engine.band, "Infatuated")
        for band, edge in (("Infatuated", 60), ("Close", 30), ("Friendly", 10), ("Neutral", -10), ("Sarcastic", -35), ("Frustrated", -60)):
            self.engine.score = edge - 3.9
            self.engine.refresh()
            self.assertEqual(self.engine.band, band)         # still holding on, 4 points of grace going down
            self.engine.score = edge - 4.1
            self.engine.refresh()
            self.assertNotEqual(self.engine.band, band)

    def test_the_live_setting_follows_each_change(self):
        for score, band in ((12, "Friendly"), (31, "Close"), (0, "Neutral"), (-12, "Sarcastic"), (-40, "Frustrated")):
            self.engine.score = score
            self.engine.band = None
            self.engine.refresh()
            self.assertEqual(self.engine.band, band)
            self.assertEqual(self.engine.settings.get("personality.mood_live"), band)

    def test_neutral_is_the_calm_middle_between_friendly_and_sarcastic(self):
        bands = []
        for score in (-50, -20, 0, 20, 40):
            self.engine.score = score
            self.engine.band = None
            self.engine.refresh()
            bands.append(self.engine.band)
        self.assertEqual(bands, ["Frustrated", "Sarcastic", "Neutral", "Friendly", "Close"])
        self.engine.score = 9
        self.engine.band = "Neutral"
        self.engine.refresh()
        self.assertEqual(self.engine.band, "Neutral")       # Friendly starts at 10
        self.engine.score = 10
        self.engine.refresh()
        self.assertEqual(self.engine.band, "Friendly")

    def test_time_together_only_while_playing(self):
        for _ in range(8):                      # active play: an event every 4 minutes
            self.send("FSDJump", {})
            self.clock.wait(4)
        self.assertGreater(self.engine.score, 0)

    def test_nothing_for_leaving_the_game_running(self):
        self.send("FSDJump", {})
        self.clock.wait(120)
        self.send("FSDJump", {})
        self.assertEqual(self.engine.score, 0)

    def test_first_matching_rule_only(self):
        self.send("CommitCrime", {"CrimeType": "murder"})
        self.assertAlmostEqual(self.engine.score, -6.0, places=1)

    def test_live_mood_is_published_and_fixed_mode_wins(self):
        self.engine.score = 40
        self.engine.refresh()
        self.assertEqual(effective_mood(self.settings), "Close")
        self.settings.set("personality.mood_mode", "fixed")
        self.settings.set("personality.mood", "Sarcastic")
        self.assertEqual(effective_mood(self.settings), "Sarcastic")

    def test_save_and_load(self):
        self.send("CommitCrime", {"CrimeType": "murder"})
        self.engine.save()
        again = MoodEngine(EventBus(), self.settings, save_path=Path(self.tmp.name) / "mood.json", clock=self.clock)
        self.assertAlmostEqual(again.score, self.engine.score, places=1)

    def test_mood_is_kept_while_closed_overnight(self):
        self.send("CommitCrime", {"CrimeType": "murder"})
        self.engine.save()
        saved = self.engine.score
        self.clock.wait(60 * 14)                                   # closed for 14 hours
        again = MoodEngine(EventBus(), self.settings, save_path=Path(self.tmp.name) / "mood.json", clock=self.clock)
        self.assertAlmostEqual(again.score, saved, places=1)

    def test_a_change_is_saved_straight_away(self):
        self.send("CommitCrime", {"CrimeType": "murder"})            # no save() call: the window could be closed now
        again = MoodEngine(EventBus(), self.settings, save_path=Path(self.tmp.name) / "mood.json", clock=self.clock)
        self.assertAlmostEqual(again.score, self.engine.score, places=1)
        self.assertNotEqual(again.score, 0)

    def test_falls_back_to_the_backup_copy(self):
        self.send("CommitCrime", {"CrimeType": "murder"})
        self.engine.save()
        self.engine.save()                                          # the second save makes the .bak
        (Path(self.tmp.name) / "mood.json").write_text("{broken", encoding="utf-8")
        again = MoodEngine(EventBus(), self.settings, save_path=Path(self.tmp.name) / "mood.json", clock=self.clock)
        self.assertNotEqual(again.score, 0)

    def test_bad_save_file_is_ignored(self):
        (Path(self.tmp.name) / "m2.json").write_text("{nonsense", encoding="utf-8")
        engine = MoodEngine(EventBus(), self.settings, save_path=Path(self.tmp.name) / "m2.json", clock=self.clock)
        self.assertEqual(engine.score, 0)


class ReactionTests(MoodBase):
    def test_reacts_once_then_cools_down(self):
        self.send("MarketSell", {"Type": "slaves"}, "low")
        self.assertEqual(len(self.said), 1)
        self.send("MarketSell", {"Type": "slaves"}, "low")
        self.assertEqual(len(self.said), 1)

    def test_stops_nagging_when_effect_is_tiny(self):
        for _ in range(8):
            self.send("MarketSell", {"Type": "slaves"}, "low")
            self.clock.wait(3)
        self.assertLess(len(self.said), 8)

    def test_no_reaction_to_critical_events(self):
        self.send("MissionFailed", {}, "critical")
        self.assertEqual(self.said, [])

    def test_info_style_is_silent_but_still_tracks(self):
        self.settings.set("personality.style", "info")
        self.send("MarketSell", {"Type": "slaves"}, "low")
        self.assertEqual(self.said, [])
        self.assertLess(self.engine.score, 0)

    def test_announces_a_mood_change(self):
        self.engine.score = 33
        self.engine.band = "Friendly"
        self.send("SellExplorationData", {"TotalEarnings": 60_000_000})
        self.assertEqual(self.engine.band, "Close")
        self.assertTrue(self.said)


class ThroughTheRealProcessor(unittest.TestCase):
    def test_slave_sale_line_from_the_journal(self):
        processor, bus, heard = make_processor()
        engine = MoodEngine(bus, Settings(Path("nope.json")).load(), persist=False)
        engine.attach()
        processor.handle_line(json.dumps({"timestamp": "2026-01-01T00:00:00Z", "event": "MarketSell", "Type": "slaves",
                                          "Count": 3, "SellPrice": 1000, "TotalSale": 3000, "BlackMarket": True}))
        self.assertLess(engine.score, 0)

    def test_mining_and_shopping_please_her(self):
        for entry in ({"event": "ProspectedAsteroid", "MotherlodeMaterial": "Painite", "Materials": []},
                      {"event": "MiningRefined", "Type": "Platinum", "Type_Localised": "Platinum"},
                      {"event": "ShipyardBuy", "ShipType": "python", "ShipPrice": 1000},
                      {"event": "ModuleBuy", "BuyItem": "x", "BuyPrice": 1}):
            processor, bus, heard = make_processor()
            engine = MoodEngine(bus, Settings(Path("nope.json")).load(), persist=False)
            engine.attach()
            processor.handle_line(json.dumps(dict(entry, timestamp="2026-01-01T00:00:00Z")))
            self.assertGreater(engine.score, 0, entry["event"])

    def test_pay_fines_is_a_known_event(self):
        processor, bus, heard = make_processor()
        engine = MoodEngine(bus, Settings(Path("nope.json")).load(), persist=False)
        engine.attach()
        processor.handle_line(json.dumps({"timestamp": "2026-01-01T00:00:00Z", "event": "PayFines", "Amount": 500, "AllFines": True}))
        self.assertGreater(engine.score, 0)

    def test_rules_file_is_valid(self):
        from personality.mood_engine import load_rules
        options, rules = load_rules()
        self.assertGreater(len(rules), 30)
        ids = [r["id"] for r in rules]
        self.assertEqual(len(ids), len(set(ids)))
        known = set(DialogueManager(paths.VOICEPACKS_DIR / "default").load().lines)
        for r in rules:
            if r.get("react"):
                self.assertIn(r["react"], known)
        for band in ("Close", "Friendly", "Neutral", "Sarcastic", "Frustrated"):
            self.assertIn("MoodShift_" + band, known)


if __name__ == "__main__":
    unittest.main()


class NotorietyTests(MoodBase):
    def setUp(self):
        super().setUp()
        self.wanted = [False]
        self.engine.wanted_provider = lambda: self.wanted[0]

    def play_for(self, minutes, step=4):
        """Active play: a harmless event every few minutes."""
        for _ in range(int(minutes / step)):
            self.send("FSDJump", {})
            self.clock.wait(step)

    def test_no_drain_when_not_wanted(self):
        self.play_for(60)
        self.assertGreaterEqual(self.engine.score, 0)

    def test_wanted_costs_points_each_hour(self):
        self.send("FSDJump", {})
        self.wanted[0] = True
        self.play_for(60)
        self.assertLess(self.engine.score, -2)
        self.assertGreater(self.engine.score, -8)         # about 6 an hour, minus a little calming

    def test_no_drain_while_away(self):
        self.send("FSDJump", {})
        self.wanted[0] = True
        self.clock.wait(8 * 60)                           # left the game running all night
        self.engine.refresh()
        self.assertGreater(self.engine.score, -1)         # only the 5 minutes after the last event count

    def test_drain_stops_at_the_floor(self):
        self.send("FSDJump", {})
        self.wanted[0] = True
        self.play_for(20 * 60)
        self.assertGreaterEqual(self.engine.score, -26)
        self.assertEqual(self.engine.band, "Sarcastic")   # notoriety alone annoys her, but never worse

    def test_arriving_wanted_costs_a_point(self):
        self.send("FSDJump", {"Wanted": True})
        self.assertLess(self.engine.score, 0)

    def test_state_tracks_wanted_from_the_journal(self):
        processor, bus, heard = make_processor()
        state = processor.state
        processor.handle_line(json.dumps({"timestamp": "2026-01-01T00:00:00Z", "event": "FSDJump", "StarSystem": "X",
                                          "JumpDist": 5.0, "Wanted": True}))
        self.assertTrue(state.wanted)
        processor.handle_line(json.dumps({"timestamp": "2026-01-01T00:01:00Z", "event": "PayBounties", "Amount": 100}))
        self.assertFalse(state.wanted)
        processor.handle_line(json.dumps({"timestamp": "2026-01-01T00:02:00Z", "event": "CommitCrime", "CrimeType": "assault",
                                          "Bounty": 400}))
        self.assertTrue(state.wanted)
        processor.handle_line(json.dumps({"timestamp": "2026-01-01T00:03:00Z", "event": "Location", "StarSystem": "Y"}))
        self.assertFalse(state.wanted)
