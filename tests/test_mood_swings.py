import unittest
from pathlib import Path

from core import paths
from core.event_bus import EventBus
from core.settings import Settings
from personality import mood_engine
from personality.dialogue import DialogueManager
from personality.mood_engine import MoodEngine


class Ev:
    def __init__(self, name, data=None, priority="normal"):
        self.name, self.data, self.priority = name, data or {}, priority


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


class SwingTests(unittest.TestCase):
    def make(self, mood_start=0.0):
        self.clock = Clock()
        self.spoken = []
        self.settings = Settings(Path("nope.json")).load()
        self.engine = MoodEngine(EventBus(), self.settings, persist=False, clock=self.clock, speak=self.spoken.append,
                                 dialogue=DialogueManager(paths.VOICEPACKS_DIR / "default").load())
        self.engine.score = mood_start * self.engine.scale
        self.engine.band = self.engine._band_for(self.engine.score, None)
        self.engine._publish_live()
        return self.engine

    def test_dying_makes_her_upset_for_five_minutes_then_she_forgives_and_returns(self):
        e = self.make(mood_start=20)                              # Friendly
        before = e.band
        self.assertEqual(before, "Friendly")
        e.on_event(Ev("Died", {"KillerName": "x"}))               # died in a fight: no score penalty
        self.assertEqual(self.settings.get("personality.mood_live"), "Upset")
        self.assertEqual(e.band, before)                          # the real mood is untouched
        self.clock.t += 4 * 60
        e.check_swing()
        self.assertEqual(self.settings.get("personality.mood_live"), "Upset")
        self.clock.t += 61
        self.assertTrue(e.check_swing())
        self.assertEqual(self.settings.get("personality.mood_live"), before)
        self.assertTrue(any("forgive" in t.lower() or "sulk" in t.lower() or "cross" in t.lower() or "upset" in t.lower()
                            for t in self.spoken), self.spoken)

    def test_unsold_data_is_lost_on_death_as_a_second_penalty(self):
        e = self.make(mood_start=20)
        for _ in range(30):
            e.on_event(Ev("Scan", {"BodyName": "x"}))
        score = e.score
        e.on_event(Ev("Died", {"KillerName": "x"}))
        self.assertLess(e.score, score)
        e.on_event(Ev("Died", {"KillerName": "x"}))               # nothing left to lose the second time
        again = e.score
        self.assertEqual(e._unsold, 0)

    def test_selling_data_first_means_nothing_to_lose(self):
        e = self.make(mood_start=20)
        for _ in range(30):
            e.on_event(Ev("Scan", {"BodyName": "x"}))
        e.on_event(Ev("SellExplorationData", {"TotalEarnings": 1000}))
        self.assertEqual(e._unsold, 0)
        score = e.score
        e.on_event(Ev("Died", {"KillerName": "x"}))
        self.assertEqual(e.score, score)

    def test_selling_at_a_loss_costs_points_and_a_profit_does_not(self):
        e = self.make(mood_start=20)
        score = e.score
        e.on_event(Ev("MarketSell", {"Count": 100, "TotalSale": 10000, "AvgPricePaid": 600}))       # lost 50000
        self.assertLess(e.score, score)
        score = e.score
        e.on_event(Ev("MarketSell", {"Count": 10, "TotalSale": 9000, "AvgPricePaid": 500}))
        self.assertEqual(e.score, score)

    def test_a_very_big_loss_also_makes_her_sarcastic_for_a_while(self):
        e = self.make(mood_start=20)
        e.on_event(Ev("MarketSell", {"Count": 100, "TotalSale": 0, "AvgPricePaid": 5000}))
        self.assertEqual(self.settings.get("personality.mood_live"), "Sarcastic")

    def test_a_rebuy_costs_points(self):
        e = self.make(mood_start=20)
        score = e.score
        e.on_event(Ev("Resurrect", {"Option": "rebuy", "Cost": 20_000_000}))
        self.assertLess(e.score, score)

    def test_good_news_gives_a_happy_swing_that_ends_without_changing_the_score(self):
        e = self.make(mood_start=0)
        e.on_event(Ev("Bounty", {"TotalReward": 5_000_000}))
        self.assertEqual(self.settings.get("personality.mood_live"), "Infatuated")
        self.clock.t += 181
        e.check_swing()
        self.assertNotEqual(self.settings.get("personality.mood_live"), "Infatuated")

    def test_a_worse_swing_is_not_replaced_by_a_milder_one(self):
        e = self.make()
        e.on_event(Ev("Died", {"KillerName": "x"}))
        e.on_event(Ev("MissionFailed", {}))
        self.assertEqual(self.settings.get("personality.mood_live"), "Upset")

    def test_the_rules_file_swings_and_lines_are_valid(self):
        swings = mood_engine.load_swings()
        self.assertGreaterEqual(len(swings), 6)
        known = set(DialogueManager(paths.VOICEPACKS_DIR / "default").load().lines)
        for s in swings:
            self.assertIn(s["forgive"], known)
        for key in ("React_DataLost", "React_Rebuy", "React_TradeLoss", "OnFootLastGrenade", "OnFootMedpack"):
            self.assertIn(key, known)

    def test_reset_clears_a_swing(self):
        e = self.make()
        e.on_event(Ev("Died", {"KillerName": "x"}))
        e.reset()
        self.assertFalse(e.swing_active())


if __name__ == "__main__":
    unittest.main()
